package com.engonow.lms.config;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.cache.CacheManager;
import org.springframework.cache.support.NoOpCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.serializer.StringRedisSerializer;

import static org.assertj.core.api.Assertions.assertThat;

class RedisConfigTest {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withUserConfiguration(
                            RedisConfig.class,
                            TestCacheManagerConfiguration.class)
                    .withPropertyValues(
                            "spring.data.redis.host=localhost",
                            "spring.data.redis.port=6379",
                            "spring.data.redis.password=",
                            "spring.data.redis.timeout=2000ms",
                            "spring.data.redis.lettuce.pool.max-active=16",
                            "spring.data.redis.lettuce.pool.max-idle=8",
                            "spring.data.redis.lettuce.pool.min-idle=2",
                            "spring.data.redis.lettuce.pool.max-wait=1000ms");

    @Test
    void stringRedisTemplateLoadsWithStringSerializers() {
        contextRunner.run(context -> {
            assertThat(context).hasBean("stringRedisTemplate");

            StringRedisTemplate redisTemplate =
                    context.getBean("stringRedisTemplate", StringRedisTemplate.class);

            assertThat(redisTemplate.getKeySerializer())
                    .isExactlyInstanceOf(StringRedisSerializer.class);
            assertThat(redisTemplate.getValueSerializer())
                    .isExactlyInstanceOf(StringRedisSerializer.class);
            assertThat(redisTemplate.getHashKeySerializer())
                    .isExactlyInstanceOf(StringRedisSerializer.class);
            assertThat(redisTemplate.getHashValueSerializer())
                    .isExactlyInstanceOf(StringRedisSerializer.class);
        });
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class TestCacheManagerConfiguration {

        @Bean
        CacheManager cacheManager() {
            return new NoOpCacheManager();
        }
    }
}
