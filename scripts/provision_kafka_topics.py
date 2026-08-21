"""
scripts/provision_kafka_topics.py
=================================
Idempotent Kafka Topic Provisioner for the ENGONOW Event-Driven Architecture.
Declares, provisions, and audits topic topology for AI Writing & Speaking evaluation pipelines.

Usage:
    python scripts/provision_kafka_topics.py --bootstrap-servers localhost:9092 --env dev
    python scripts/provision_kafka_topics.py --bootstrap-servers kafka:29092 --env prod --replication-factor 3
"""

import argparse
import logging
import os
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("KAFKA_TOPIC_PROVISIONER")

# Time constants in milliseconds
RETENTION_1_DAY_MS = 86_400_000
RETENTION_7_DAYS_MS = 604_800_000
RETENTION_14_DAYS_MS = 1_209_600_000
RETENTION_30_DAYS_MS = 2_592_000_000


@dataclass
class TopicDefinition:
    """Canonical declaration of a Kafka topic within the ENGONOW topology."""
    name: str
    num_partitions: int
    replication_factor_dev: int = 1
    replication_factor_prod: int = 3
    retention_ms: int = RETENTION_7_DAYS_MS
    cleanup_policy: str = "delete"
    description: str = ""

    def get_configs(self) -> Dict[str, str]:
        return {
            "cleanup.policy": self.cleanup_policy,
            "retention.ms": str(self.retention_ms),
            "compression.type": "producer",
        }


# Canonical Topology Specification
CORE_TOPICS: List[TopicDefinition] = [
    # -------------------------------------------------------------
    # IELTS Writing Evaluation Pipeline
    # -------------------------------------------------------------
    TopicDefinition(
        name="engonow.writing.evaluation-requested.v1",
        num_partitions=12,
        retention_ms=RETENTION_7_DAYS_MS,
        description="Ingestion queue for student essay evaluation requests dispatched by Java Outbox Relay.",
    ),
    TopicDefinition(
        name="engonow.writing.evaluation-completed.v1",
        num_partitions=12,
        retention_ms=RETENTION_7_DAYS_MS,
        description="Event emitted when Python AI Worker successfully finishes Gemini 2.5 Flash evaluation.",
    ),
    TopicDefinition(
        name="engonow.writing.evaluation-failed.v1",
        num_partitions=6,
        retention_ms=RETENTION_14_DAYS_MS,
        description="Dead-letter / error notification topic for terminal writing evaluation failures.",
    ),
    # -------------------------------------------------------------
    # IELTS Speaking Evaluation Pipeline
    # -------------------------------------------------------------
    TopicDefinition(
        name="engonow.speaking.evaluation-requested.v1",
        num_partitions=12,
        retention_ms=RETENTION_7_DAYS_MS,
        description="Ingestion queue for speaking evaluation requests (Claim-Check remote audio pointer).",
    ),
    TopicDefinition(
        name="engonow.speaking.evaluation-completed.v1",
        num_partitions=12,
        retention_ms=RETENTION_7_DAYS_MS,
        description="Event emitted when multi-modal acoustic AI worker completes speaking evaluation.",
    ),
    TopicDefinition(
        name="engonow.speaking.evaluation-failed.v1",
        num_partitions=6,
        retention_ms=RETENTION_14_DAYS_MS,
        description="Error notification topic for speaking evaluation failures.",
    ),
]


def generate_full_topology() -> List[TopicDefinition]:
    """Expands core topics to include standard DLQ and delayed retry topics."""
    full_list: List[TopicDefinition] = []

    for base in CORE_TOPICS:
        full_list.append(base)

        # DLQ topic (Dead Letter Queue, 30-day retention)
        dlq_topic = TopicDefinition(
            name=f"{base.name}.dlq",
            num_partitions=3,
            retention_ms=RETENTION_30_DAYS_MS,
            description=f"Dead letter queue for poisoned messages from {base.name}",
        )
        full_list.append(dlq_topic)

        # Retry topic for requesting pipelines (1-day retention)
        if "requested" in base.name:
            retry_topic = TopicDefinition(
                name=f"{base.name}.retry.30s",
                num_partitions=3,
                retention_ms=RETENTION_1_DAY_MS,
                description=f"30-second backoff retry queue for transient failures from {base.name}",
            )
            full_list.append(retry_topic)

    return full_list


def provision_topics(
    bootstrap_servers: str,
    environment: str = "dev",
    explicit_replication: Optional[int] = None,
    dry_run: bool = False,
) -> bool:
    """
    Connects to Kafka AdminClient, queries existing topics, and idempotently creates missing topics.
    """
    logger.info("=" * 80)
    logger.info(" ENGONOW KAFKA TOPIC TOPOLOGY PROVISIONER (Sprint 2 / EDA Phase 0)")
    logger.info("=" * 80)
    logger.info("Target Bootstrap Servers : %s", bootstrap_servers)
    logger.info("Target Environment       : %s", environment.upper())
    logger.info("Dry Run Mode             : %s", dry_run)

    topology = generate_full_topology()
    logger.info("Total Declared Topics in Topology: %d", len(topology))

    try:
        from kafka.admin import KafkaAdminClient, NewTopic
        from kafka.errors import TopicAlreadyExistsError
    except ImportError:
        logger.error(
            "kafka-python library not found. Please install via: pip install kafka-python-ng"
        )
        return False

    try:
        admin_client = KafkaAdminClient(
            bootstrap_servers=bootstrap_servers,
            client_id="engonow-topic-provisioner",
            request_timeout_ms=10000,
        )
    except Exception as ex:
        logger.error("Failed to connect to Kafka broker at '%s': %s", bootstrap_servers, ex)
        logger.warning(
            "If running locally, ensure Kafka container is up (docker compose -f docker-compose.kafka.yml up -d)."
        )
        return False

    try:
        existing_topics = set(admin_client.list_topics())
        logger.info("Found %d existing topic(s) on cluster.", len(existing_topics))

        new_topics_to_create: List[NewTopic] = []
        already_existing_count = 0

        for t in topology:
            rep_factor = (
                explicit_replication
                if explicit_replication is not None
                else (t.replication_factor_prod if environment == "prod" else t.replication_factor_dev)
            )

            if t.name in existing_topics:
                already_existing_count += 1
                logger.info("[EXISTS] %-52s | Partitions: %2d", t.name, t.num_partitions)
            else:
                logger.info(
                    "[CREATE] %-52s | Partitions: %2d | Rep: %d | Retention: %dd",
                    t.name,
                    t.num_partitions,
                    rep_factor,
                    t.retention_ms // (86_400_000),
                )
                new_topics_to_create.append(
                    NewTopic(
                        name=t.name,
                        num_partitions=t.num_partitions,
                        replication_factor=rep_factor,
                        topic_configs=t.get_configs(),
                    )
                )

        if dry_run:
            logger.info("DRY-RUN: %d topic(s) would be created. Exiting without changes.", len(new_topics_to_create))
            return True

        if not new_topics_to_create:
            logger.info("SUCCESS: All %d declared topics already exist. Zero changes required.", len(topology))
            return True

        logger.info("Provisioning %d new topic(s)...", len(new_topics_to_create))
        admin_client.create_topics(new_topics=new_topics_to_create, validate_only=False)
        logger.info("SUCCESS: Successfully provisioned %d new topic(s).", len(new_topics_to_create))
        return True

    except Exception as ex:
        logger.error("Error during topic provisioning: %s", ex, exc_info=True)
        return False
    finally:
        admin_client.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Provision and audit canonical Kafka topics for ENGONOW LMS."
    )
    parser.add_argument(
        "--bootstrap-servers",
        type=str,
        default=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
        help="Kafka bootstrap server address (default: localhost:9092)",
    )
    parser.add_argument(
        "--env",
        choices=["dev", "prod"],
        default=os.getenv("APP_ENV", "dev"),
        help="Environment target (dev uses rep=1, prod uses rep=3)",
    )
    parser.add_argument(
        "--replication-factor",
        type=int,
        default=None,
        help="Override replication factor for all provisioned topics",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Audit cluster state without creating topics",
    )

    args = parser.parse_args()

    success = provision_topics(
        bootstrap_servers=args.bootstrap_servers,
        environment=args.env,
        explicit_replication=args.replication_factor,
        dry_run=args.dry_run,
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
