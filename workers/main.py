import asyncio
import logging
import signal
import os
import asyncpg
from workers.writing_consumer import WritingEvaluationConsumer
from providers.gemini_writing_provider import GeminiWritingProvider

# Set up logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("workers.main")

async def main():
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/engonow_lms"
    )
    bootstrap_servers = os.getenv(
        "KAFKA_BOOTSTRAP_SERVERS",
        "localhost:9092"
    )
    concurrency_limit = int(os.getenv(
        "AI_MAX_CONCURRENT_EVALUATIONS",
        "8"
    ))
    gemini_api_key = os.getenv("GEMINI_API_KEY", "MOCK_GEMINI_KEY")

    logger.info("Initializing asyncpg connection pool to PostgreSQL...")
    try:
        db_pool = await asyncpg.create_pool(
            dsn=database_url,
            min_size=2,
            max_size=concurrency_limit + 5
        )
    except Exception as e:
        logger.critical("Failed to connect to database: %s", str(e))
        return

    logger.info("Initializing Gemini Writing Provider...")
    # Inject API key and model config if necessary
    writing_provider = GeminiWritingProvider(api_key=gemini_api_key)

    consumer_worker = WritingEvaluationConsumer(
        db_pool=db_pool,
        writing_provider=writing_provider,
        concurrency_limit=concurrency_limit,
        bootstrap_servers=bootstrap_servers
    )

    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    def handle_signal(sig):
        logger.info("Received termination signal %s. Initiating graceful shutdown...", sig.name)
        shutdown_event.set()

    # Trap standard termination signals
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda s=sig: handle_signal(s))
        except NotImplementedError:
            # Signal handling may not be fully supported in Windows command line testing in some environments
            pass

    await consumer_worker.start()

    # Keep running until signal received
    try:
        await shutdown_event.wait()
    except asyncio.CancelledError:
        pass

    logger.info("Shutting down worker components...")
    
    # Trigger clean drain of consumers, connections, and background tasks
    try:
        await asyncio.wait_for(consumer_worker.stop(), timeout=60.0)
    except asyncio.TimeoutError:
        logger.error("Graceful shutdown timed out. Forcing termination.")
        
    await db_pool.close()
    logger.info("Cleanup completed. Exiting worker.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Worker terminated manually")
