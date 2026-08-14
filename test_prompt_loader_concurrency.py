"""
test_prompt_loader_concurrency.py
=================================
Concurrency and race-condition stress test for prompt loader caching and cache-clearing locks.
"""

import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from providers.config import clear_prompt_cache, load_prompt_file


class TestPromptLoaderConcurrency(unittest.IsolatedAsyncioTestCase):
    """Stress tests for thread safety and non-blocking asynchronous prompt loading."""

    async def test_concurrent_load_and_clear_cache(self):
        """
        Triggers 50 concurrent asyncio tasks reading prompt files while simultaneously
        invoking clear_prompt_cache to ensure the thread lock prevents race conditions.
        """
        system_path = "providers/prompts/writing_system.txt"
        user_path = "providers/prompts/writing_user.txt"

        async def worker(index: int) -> str:
            path = system_path if index % 2 == 0 else user_path
            content = await load_prompt_file(path)
            self.assertTrue(len(content) > 0)

            if index % 5 == 0:
                clear_prompt_cache()

            reloaded = await load_prompt_file(path)
            self.assertEqual(content, reloaded)
            return content

        tasks = [asyncio.create_task(worker(i)) for i in range(50)]
        results = await asyncio.gather(*tasks, return_exceptions=False)

        self.assertEqual(len(results), 50)
        for res in results:
            self.assertIsInstance(res, str)
            self.assertTrue(len(res) > 20)

    async def test_hot_reload_mutation_under_load(self):
        """
        Simulates live prompt file mutations under high concurrent read load,
        verifying that clear_prompt_cache propagates the new template correctly
        without raising exceptions or corrupting reads.
        """
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt", encoding="utf-8") as tf:
            tf.write("Initial Version 1.0 Content")
            temp_path = tf.name

        try:
            # 1. Warm-up cache
            v1 = await load_prompt_file(temp_path)
            self.assertEqual(v1, "Initial Version 1.0 Content")

            # 2. Mutate file on disk
            Path(temp_path).write_text("Mutated Version 2.0 Content", encoding="utf-8")

            # 3. Concurrent workers reading while one worker triggers clear_prompt_cache
            async def reader(idx: int) -> str:
                if idx == 25:
                    clear_prompt_cache()
                return await load_prompt_file(temp_path)

            tasks = [asyncio.create_task(reader(i)) for i in range(50)]
            results = await asyncio.gather(*tasks, return_exceptions=False)

            self.assertEqual(len(results), 50)
            # After clearing, fresh reads must get the updated version
            clear_prompt_cache()
            v2 = await load_prompt_file(temp_path)
            self.assertEqual(v2, "Mutated Version 2.0 Content")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


if __name__ == "__main__":
    unittest.main()
