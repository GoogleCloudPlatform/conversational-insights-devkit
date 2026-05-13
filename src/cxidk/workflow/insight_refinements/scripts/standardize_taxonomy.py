# Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.
"""
Taxonomy Standardization Utility.

This script fetches unique L2 categories from BigQuery and uses Gemini
to cluster them into a standardized taxonomy, saving the results to a JSON file.
"""

import argparse
import json
import logging
import sys
import time
import uuid
import pandas as pd
from typing import Optional
from pydantic_settings import BaseSettings
from cxidk.workflow.insight_refinements.taxonomy_utils import TaxonomyStandardizer
from cxidk.workflow.insight_refinements.schemas.input import (
    BatchAnalysisInput,
    GCPConfig,
    CCAIConfig,
    BigQueryConfig,
    LLMConfig,
    TopicRefinementConfig,
)
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

class StandardizerSettings(BaseSettings):
    """Settings for the Taxonomy Standardizer."""
    gcp_project_id: str
    gcp_project_number: str
    gcp_location_id: str = "us-central1"
    
    bq_project_id: Optional[str] = None
    bq_dataset_id: str
    bq_l2_taxonomy_table: str = "l2_taxonomy_results"
    
    llm_model_name: str = "gemini-3.1-flash-lite-preview"
    llm_location_id: str = "global"
    ccai_issue_model_id: str

def parse_args():
    parser = argparse.ArgumentParser(description="Standardize exploratory L2 taxonomy.")
    parser.add_argument(
        "--output", 
        default="approved_taxonomy.json",
        help="Path to save the standardized taxonomy mapping JSON."
    )
    return parser.parse_args()

def main():
    args = parse_args()
    
    try:
        settings = StandardizerSettings()
    except Exception as e:
        logger.error(f"Missing configuration: {e}")
        sys.exit(1)

    # Construct the internal config object
    config = BatchAnalysisInput(
        gcp=GCPConfig(
            project_id=settings.gcp_project_id,
            project_number=settings.gcp_project_number,
            location_id=settings.gcp_location_id,
        ),
        ccai=CCAIConfig(
            scorecard_id="n/a",
        ),
        llm=LLMConfig(
            model_name=settings.llm_model_name,
            location_id=settings.llm_location_id,
        ),
        bigquery=BigQueryConfig(
            project_id=settings.bq_project_id,
            dataset_id=settings.bq_dataset_id,
            staging_table_id="dummy",
            main_table_id="dummy",
        ),
        topic_refinement=TopicRefinementConfig(
            issue_model_id=settings.ccai_issue_model_id,
            l2_taxonomy_table=settings.bq_l2_taxonomy_table,
        ),
    )

    standardizer = TaxonomyStandardizer(config)
    
    # 1. Fetch unique categories from BQ
    try:
        unique_cats = standardizer.fetch_unique_categories()
        if not unique_cats:
            logger.info("No unique categories found in BigQuery. Exiting.")
            return
        
        logger.info(f"Found {len(unique_cats)} unique raw categories.")
    except Exception as e:
        logger.error(f"Failed to fetch categories: {e}")
        sys.exit(1)

    # 2. Call Gemini for standardization
    try:
        start_time = time.time()
        mapping_data, input_tokens, output_tokens = standardizer.generate_standardized_mapping(unique_cats)
        latency_ms = (time.time() - start_time) * 1000
        
        # 3. Save to file
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(mapping_data, f, indent=2)
        
        logger.info(f"Successfully saved standardized taxonomy to {args.output}")
        logger.info(f"Master Categories: {mapping_data.get('master_categories', [])}")
        
        # 4. Write to BigQuery Audit Table
        audit_entry = {
            "run_id": str(uuid.uuid4()),
            "conversation_id": "system-taxonomy-standardization",
            "status": "success",
            "error_message": None,
            "latency_ms": latency_ms,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens
        }
        audit_df = pd.DataFrame([audit_entry])
        standardizer.bq_client.write_audit_log(audit_df)
        
    except Exception as e:
        logger.error(f"Standardization failed: {e}")
        # Log failure if possible
        try:
            fail_entry = {
                "run_id": str(uuid.uuid4()),
                "conversation_id": "system-taxonomy-standardization",
                "status": "error",
                "error_message": str(e),
                "latency_ms": 0,
                "input_tokens": 0,
                "output_tokens": 0
            }
            standardizer.bq_client.write_audit_log(pd.DataFrame([fail_entry]))
        except Exception:
            pass
        sys.exit(1)

if __name__ == "__main__":
    main()
