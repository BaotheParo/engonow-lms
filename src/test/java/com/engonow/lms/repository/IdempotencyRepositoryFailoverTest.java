package com.engonow.lms.repository;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentMatchers;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.redis.RedisConnectionFailureException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.RedisScript;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class IdempotencyRepositoryFailoverTest {

    @Mock
    private StringRedisTemplate stringRedisTemplate;

    @InjectMocks
    private IdempotencyRepository idempotencyRepository;

    @Test
    void testTryLock_WhenRedisThrowsException_ShouldFallbackToLocalMapAndSucceed() {
        when(stringRedisTemplate.execute(
                ArgumentMatchers.<RedisScript<Long>>any(),
                ArgumentMatchers.<String>anyList(),
                any()))
                .thenThrow(new RedisConnectionFailureException("Connection refused"));

        String key = "test:failover:key";
        long ttlMillis = 5_000L;

        boolean firstAttemptAcquired =
                idempotencyRepository.tryLock(key, ttlMillis);
        boolean secondAttemptAcquired =
                idempotencyRepository.tryLock(key, ttlMillis);

        assertTrue(firstAttemptAcquired);
        assertFalse(secondAttemptAcquired);
    }
}
