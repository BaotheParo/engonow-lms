package com.engonow.lms.config;

import io.lettuce.core.api.StatefulConnection;
import org.apache.commons.pool2.impl.GenericObjectPoolConfig;
import org.springframework.boot.autoconfigure.data.redis.RedisProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.RedisPassword;
import org.springframework.data.redis.connection.RedisStandaloneConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceClientConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;
import org.springframework.data.redis.connection.lettuce.LettucePoolingClientConfiguration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.serializer.StringRedisSerializer;
import org.springframework.util.StringUtils;

/**
 * Configures centralized Redis access for distributed application state.
 *
 * <p>Lettuce uses non-blocking network I/O internally, while its connection factory and
 * {@link StringRedisTemplate} are thread-safe and can be shared across application threads.
 * Pool limits protect Redis and the application from unbounded connection growth.</p>
 */
@Configuration
@EnableCaching
@EnableConfigurationProperties(RedisProperties.class)
public class RedisConfig {

    /**
     * Creates the pooled Lettuce connection factory from environment-backed Spring properties.
     *
     * @param redisProperties type-safe Redis and Lettuce pool properties
     * @return thread-safe Redis connection factory
     */
    @Bean
    public RedisConnectionFactory redisConnectionFactory(
            RedisProperties redisProperties) {

        RedisStandaloneConfiguration serverConfiguration =
                new RedisStandaloneConfiguration(
                        redisProperties.getHost(),
                        redisProperties.getPort());
        serverConfiguration.setDatabase(redisProperties.getDatabase());
        if (StringUtils.hasText(redisProperties.getPassword())) {
            serverConfiguration.setPassword(
                    RedisPassword.of(redisProperties.getPassword()));
        }

        RedisProperties.Pool poolProperties =
                redisProperties.getLettuce().getPool();
        GenericObjectPoolConfig<StatefulConnection<?, ?>> poolConfiguration =
                new GenericObjectPoolConfig<>();
        poolConfiguration.setMaxTotal(poolProperties.getMaxActive());
        poolConfiguration.setMaxIdle(poolProperties.getMaxIdle());
        poolConfiguration.setMinIdle(poolProperties.getMinIdle());
        poolConfiguration.setMaxWait(poolProperties.getMaxWait());

        LettuceClientConfiguration clientConfiguration =
                LettucePoolingClientConfiguration.builder()
                        .commandTimeout(redisProperties.getTimeout())
                        .poolConfig(poolConfiguration)
                        .build();

        return new LettuceConnectionFactory(serverConfiguration, clientConfiguration);
    }

    /**
     * Creates a Redis template with an explicit UTF-8 string serialization contract.
     *
     * @param connectionFactory pooled Lettuce connection factory
     * @return reusable, thread-safe string Redis template
     */
    @Bean(name = "stringRedisTemplate")
    public StringRedisTemplate stringRedisTemplate(
            RedisConnectionFactory connectionFactory) {

        StringRedisTemplate redisTemplate = new StringRedisTemplate();
        redisTemplate.setConnectionFactory(connectionFactory);
        redisTemplate.setKeySerializer(new StringRedisSerializer());
        redisTemplate.setValueSerializer(new StringRedisSerializer());
        redisTemplate.setHashKeySerializer(new StringRedisSerializer());
        redisTemplate.setHashValueSerializer(new StringRedisSerializer());
        return redisTemplate;
    }
}
