package com.engonow.lms.entity;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.Setter;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

import java.time.LocalDateTime;

/**
 * Abstract superclass providing JPA Auditing timestamps to all entities.
 *
 * Design notes:
 *  - @MappedSuperclass: columns are inlined into each child table (no separate table).
 *  - @EntityListeners(AuditingEntityListener.class): hooks Spring Data's auditing
 *    infrastructure; requires @EnableJpaAuditing on a @Configuration class.
 *  - updatable=false on createdAt ensures INSERT-only semantics at the DB level.
 */
@Getter
@Setter
@MappedSuperclass
@EntityListeners(AuditingEntityListener.class)
public abstract class BaseEntity {

    @CreatedDate
    @Column(name = "created_at", nullable = false, updatable = false)
    private LocalDateTime createdAt;

    @LastModifiedDate
    @Column(name = "updated_at", nullable = false)
    private LocalDateTime updatedAt;
}
