package com.engonow.lms.repository;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

@Component
public class IdempotencyRepository {

    private final Map<String, Long> lockMap = new ConcurrentHashMap<>();

    /**
     * Attempts to acquire an idempotency lock for the given key.
     * Uses atomic compute() to perform an O(1) lock check and lazy validation of expired locks.
     *
     * @param key       the unique idempotency key
     * @param ttlMillis time-to-live in milliseconds
     * @return true if the lock was successfully acquired, false if it is currently locked
     */
    public boolean tryLock(String key, long ttlMillis) {
        long now = System.currentTimeMillis();
        long expireAt = now + ttlMillis;

        Long result = lockMap.compute(key, (k, existingExpireAt) -> {
            if (existingExpireAt == null || existingExpireAt < now) {
                return expireAt;
            }
            return existingExpireAt;
        });

        return result == expireAt;
    }

    /**
     * Periodically cleans up expired keys from the in-memory store in the background.
     * Runs every 1 minute to prevent memory exhaustion under high load.
     */
    @Scheduled(fixedRate = 60000)
    public void cleanupExpiredKeys() {
        long now = System.currentTimeMillis();
        lockMap.entrySet().removeIf(entry -> entry.getValue() < now);
    }

    /**
     * Manually releases the lock for the given key.
     *
     * @param key the unique idempotency key to release
     */
    public void releaseLock(String key) {
        lockMap.remove(key);
    }
}
