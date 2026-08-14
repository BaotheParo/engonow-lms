package com.engonow.lms.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;

/**
 * Enables Spring Data JPA Auditing globally.
 *
 * Required for @CreatedDate and @LastModifiedDate on BaseEntity to be populated
 * automatically by the AuditingEntityListener.
 *
 * Kept in its own @Configuration class (separate from SecurityConfig) to avoid
 * circular dependency issues when combining Spring Security + JPA Auditing.
 */
@Configuration
@EnableJpaAuditing
@EnableJpaRepositories(basePackages = {"com.engonow.lms.repository", "com.engonow.lms.writing.repository"})
public class JpaAuditingConfig {
    // No beans needed — @EnableJpaAuditing does all the wiring.
}
