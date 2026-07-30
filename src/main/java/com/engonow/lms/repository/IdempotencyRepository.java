package com.engonow.lms.repository;

import com.engonow.lms.exception.IdempotencyException;
import org.springframework.core.io.ClassPathResource;
import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.RedisScript;
import org.springframework.stereotype.Component;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Manages cluster-wide idempotency locks in Redis.
 */
@Component
public class IdempotencyRepository {

    private static final Logger log =
            LoggerFactory.getLogger(IdempotencyRepository.class);

    private static final Long LOCK_ACQUIRED = 1L;
    private static final Long ALREADY_COMPLETED = 2L;
    private static final Long CURRENTLY_PROCESSING = 3L;
    private static final Long TRANSITION_COMPLETED = 1L;

    private static final RedisScript<Long> TRY_ACQUIRE_LOCK_SCRIPT =
            RedisScript.of(
                    new ClassPathResource("redis/tryAcquireLock.lua"),
                    Long.class);

    private static final RedisScript<Long> TRANSITION_TO_COMPLETE_SCRIPT =
            RedisScript.of(
                    new ClassPathResource("redis/transitionToComplete.lua"),
                    Long.class);

    private final StringRedisTemplate stringRedisTemplate;
    private final Map<String, Long> localFallbackMap = new ConcurrentHashMap<>();

    public IdempotencyRepository(StringRedisTemplate stringRedisTemplate) {
        this.stringRedisTemplate = stringRedisTemplate;
    }

    /**
     * Attempts to acquire an idempotency lock for the given key.
     *
     * <p>The Lua script atomically checks the current state, creates a PROCESSING state,
     * and applies the TTL when no state exists.</p>
     *
     * @param key       the unique idempotency key
     * @param ttlMillis time-to-live in milliseconds
     * @return true when the PROCESSING state was created
     * @throws IdempotencyException when the request is already completed or processing
     */
    public boolean tryLock(String key, long ttlMillis) {
        Long result;
        try {
            result = stringRedisTemplate.execute(
                    TRY_ACQUIRE_LOCK_SCRIPT,
                    List.of(key),
                    Long.toString(ttlMillis));
        } catch (DataAccessException ex) {
            return handleTryLockFailover(key, ttlMillis, ex);
        } catch (Exception ex) {
            return handleTryLockFailover(key, ttlMillis, ex);
        }

        if (LOCK_ACQUIRED.equals(result)) {
            return true;
        }

        if (ALREADY_COMPLETED.equals(result) || CURRENTLY_PROCESSING.equals(result)) {
            throw new IdempotencyException(
                    "Request is already completed or currently processing.");
        }

        return false;
    }

    /**
     * Atomically transitions a PROCESSING lock to COMPLETED while retaining its remaining TTL.
     *
     * @param key the unique idempotency key
     * @param ttlMillis fallback TTL when the Redis key has no active expiration
     * @throws IllegalStateException when the lock is missing or is not PROCESSING
     */
    public void completeLock(String key, long ttlMillis) {
        Long result;
        try {
            result = stringRedisTemplate.execute(
                    TRANSITION_TO_COMPLETE_SCRIPT,
                    List.of(key),
                    Long.toString(ttlMillis));
        } catch (DataAccessException ex) {
            handleCompleteLockFailover(key, ttlMillis, ex);
            return;
        } catch (Exception ex) {
            handleCompleteLockFailover(key, ttlMillis, ex);
            return;
        }

        if (!TRANSITION_COMPLETED.equals(result)) {
            throw new IllegalStateException(
                    "Idempotency lock could not transition from PROCESSING to COMPLETED.");
        }
    }

    /**
     * Manually releases the lock for the given key.
     *
     * @param key the unique idempotency key to release
     */
    public void releaseLock(String key) {
        try {
            stringRedisTemplate.delete(key);
        } catch (DataAccessException ex) {
            logReleaseLockFailover(key, ex);
        } catch (Exception ex) {
            logReleaseLockFailover(key, ex);
        } finally {
            releaseLocalFallbackLock(key);
        }
    }

    private boolean handleTryLockFailover(
            String key,
            long ttlMillis,
            Exception ex) {

        log.error(
                "[IDEMPOTENCY FAILOVER] Redis unavailable during tryLock for key: {}. "
                        + "Falling back to In-Memory Lock. Error: {}",
                key,
                ex.getMessage());
        return tryLocalFallbackLock(key, ttlMillis);
    }

    private void handleCompleteLockFailover(
            String key,
            long ttlMillis,
            Exception ex) {

        log.error(
                "[IDEMPOTENCY FAILOVER] Redis unavailable during completeLock for key: {}. "
                        + "Error: {}",
                key,
                ex.getMessage());

        long now = System.currentTimeMillis();
        long expireAt = now + ttlMillis;
        localFallbackMap.compute(
                key,
                (ignored, existingExpireAt) ->
                        existingExpireAt != null && existingExpireAt > now
                                ? existingExpireAt
                                : expireAt);
    }

    private void logReleaseLockFailover(String key, Exception ex) {
        log.warn(
                "[IDEMPOTENCY FAILOVER] Redis unavailable during releaseLock for key: {}. "
                        + "Error: {}",
                key,
                ex.getMessage());
    }

    private boolean tryLocalFallbackLock(String key, long ttlMillis) {
        long now = System.currentTimeMillis();
        long expireAt = now + ttlMillis;
        AtomicBoolean acquired = new AtomicBoolean(false);

        localFallbackMap.compute(key, (ignored, existingExpireAt) -> {
            if (existingExpireAt == null || existingExpireAt <= now) {
                acquired.set(true);
                return expireAt;
            }
            return existingExpireAt;
        });

        return acquired.get();
    }

    private void releaseLocalFallbackLock(String key) {
        localFallbackMap.remove(key);
    }
}
