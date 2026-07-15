import logging
from datetime import datetime
from typing import List, Optional
from sqlalchemy import text
from sqlalchemy.orm import Session
from db.models import Entity, AutomationProposal
from connectors.base import AdsConnector
from analysis.tier1_rules import get_wasted_spend, get_underperforming_entities

logger = logging.getLogger(__name__)

def _get_campaign_native_id_for_entity(session: Session, entity_key: str, level: str) -> Optional[str]:
    """
    Traverse the entity parent keys to find the root campaign's native_id.
    """
    ent = session.query(Entity).filter_by(entity_key=entity_key).first()
    if not ent:
        return None
        
    if level == "campaign":
        return ent.native_id
    elif level == "adgroup":
        if not ent.parent_key:
            return None
        camp = session.query(Entity).filter_by(entity_key=ent.parent_key).first()
        return camp.native_id if camp else None
    elif level in ("ad", "keyword", "search_term"):
        if not ent.parent_key:
            return None
        # Parent is adgroup
        adg = session.query(Entity).filter_by(entity_key=ent.parent_key).first()
        if not adg or not adg.parent_key:
            return None
        # Grandparent is campaign
        camp = session.query(Entity).filter_by(entity_key=adg.parent_key).first()
        return camp.native_id if camp else None
        
    return None

def generate_proposals(session: Session) -> int:
    """
    Scans rules diagnostics and generates new pending automation proposals.
    Deduplicates against existing database proposals.
    
    :param session: SQLAlchemy database session.
    :return: The count of new proposals created.
    """
    new_proposals_count = 0

    # 1. Identify Wasted Spend Search Terms
    logger.info("Scanning for wasted search term spend...")
    wasted = get_wasted_spend(session, min_cost=50.0)
    for w in wasted:
        entity_key = w["entity_key"]
        
        # Traverse hierarchy to find the native campaign ID
        campaign_id = _get_campaign_native_id_for_entity(session, entity_key, "search_term")
        if not campaign_id:
            logger.warning(f"Could not resolve campaign ID for search term entity '{entity_key}'")
            continue
            
        action_type = "add_negative_keyword"
        details = {
            "campaign_id": campaign_id,
            "keyword": w["search_term_name"]
        }
        
        # Check if proposal already exists
        exists = session.query(AutomationProposal).filter(
            AutomationProposal.target_entity_key == entity_key,
            AutomationProposal.action_type == action_type
        ).first()
        
        if not exists:
            logger.info(f"Proposing negative keyword block for: '{w['search_term_name']}' in campaign '{campaign_id}'")
            proposal = AutomationProposal(
                provider=w["provider"],
                account_id=w["account_id"],
                action_type=action_type,
                target_entity_key=entity_key,
                details=details,
                status="pending",
                reason=f"Wasted spend check failed: search term spent ${w['cost']:.2f} with 0 conversions."
            )
            session.add(proposal)
            new_proposals_count += 1

    # 2. Identify CPA Underperforming Entities
    logger.info("Scanning for CPA underperforming campaigns, ad groups, or ads...")
    underperformers = get_underperforming_entities(session, min_entity_cost=50.0, multiplier=2.0)
    for u in underperformers:
        entity_key = u["entity_key"]
        action_type = "pause_entity"
        details = {
            "level": u["level"],
            "native_id": entity_key.split(":")[-1]  # Extract Native ID
        }
        
        # Check if proposal already exists
        exists = session.query(AutomationProposal).filter(
            AutomationProposal.target_entity_key == entity_key,
            AutomationProposal.action_type == action_type
        ).first()
        
        if not exists:
            logger.info(f"Proposing entity pause for: {u['level']} '{u['entity_name']}' due to high CPA")
            proposal = AutomationProposal(
                provider=u["provider"],
                account_id=u["account_id"],
                action_type=action_type,
                target_entity_key=entity_key,
                details=details,
                status="pending",
                reason=f"CPA check failed: Entity CPA is ${u['entity_cpa']:.2f} which is > 2.0x average CPA (${u['account_avg_cpa']:.2f})."
            )
            session.add(proposal)
            new_proposals_count += 1

    if new_proposals_count > 0:
        session.commit()
        logger.info(f"Successfully generated {new_proposals_count} new pending proposals.")
        
    return new_proposals_count

def execute_approved_proposals(session: Session, connectors: List[AdsConnector]) -> int:
    """
    Scans for 'approved' proposals, dispatches them to correct connectors,
    and updates status to 'executed' (or 'failed' on API failures).
    
    :param session: SQLAlchemy database session.
    :param connectors: List of platform connectors.
    :return: Count of successfully executed proposals.
    """
    approved = session.query(AutomationProposal).filter_by(status="approved").all()
    if not approved:
        logger.info("No approved proposals found for execution.")
        return 0

    connectors_by_provider = {c.provider: c for c in connectors}
    executed_count = 0

    for proposal in approved:
        provider = proposal.provider
        connector = connectors_by_provider.get(provider)
        if not connector:
            logger.error(f"Cannot execute proposal {proposal.id}: connector not found for provider '{provider}'")
            proposal.status = "failed"
            proposal.reason = f"Connector not registered for provider '{provider}'."
            continue

        logger.info(f"Executing approved proposal {proposal.id} ({proposal.action_type}) for account {proposal.account_id}")
        success = False
        
        try:
            if proposal.action_type == "add_negative_keyword":
                success = connector.add_negative_keyword(
                    account_id=proposal.account_id,
                    campaign_id=proposal.details["campaign_id"],
                    keyword=proposal.details["keyword"]
                )
            elif proposal.action_type == "pause_entity":
                success = connector.pause_entity(
                    account_id=proposal.account_id,
                    level=proposal.details["level"],
                    native_id=proposal.details["native_id"]
                )
            elif proposal.action_type == "adjust_budget":
                success = connector.update_budget(
                    account_id=proposal.account_id,
                    campaign_id=proposal.details["campaign_id"],
                    new_budget=proposal.details["new_budget"]
                )
        except Exception as e:
            logger.error(f"Error executing write action on connector: {e}", exc_info=True)
            success = False

        if success:
            proposal.status = "executed"
            proposal.reviewed_at = datetime.utcnow()
            executed_count += 1
            logger.info(f"Proposal {proposal.id} executed successfully.")
        else:
            proposal.status = "failed"
            proposal.reviewed_at = datetime.utcnow()
            logger.error(f"Proposal {proposal.id} execution failed.")

    session.commit()
    return executed_count
