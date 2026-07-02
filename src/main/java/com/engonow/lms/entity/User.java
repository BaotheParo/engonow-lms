package com.engonow.lms.entity;

import jakarta.persistence.*;
import lombok.*;

import java.util.HashSet;
import java.util.Set;

/**
 * Core User entity for Authentication & Authorization.
 *
 * Design notes:
 *  - Roles: @ManyToMany with LAZY fetch. We load roles only when needed (e.g.,
 *    during Spring Security authentication), not on every User query.
 *    FetchType.EAGER on a collection is almost always a performance antipattern.
 *
 *  - Join table "user_roles" uses a composite PK (user_id, role_id).
 *    No separate entity needed for this pure join table.
 *
 *  - @Column(unique=true) on email enforces uniqueness at DB level as a safety net
 *    beyond application-level checks.
 *
 *  - password field stores BCrypt hash; plain text is NEVER stored.
 *
 *  - Extends BaseEntity for createdAt / updatedAt audit columns.
 */
@Entity
@Table(name = "users",
       uniqueConstraints = {
           @UniqueConstraint(name = "uk_user_email",    columnNames = "email"),
           @UniqueConstraint(name = "uk_user_username", columnNames = "username")
       })
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
@com.fasterxml.jackson.annotation.JsonIgnoreProperties({"hibernateLazyInitializer", "handler"})
public class User extends BaseEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "username", nullable = false, length = 60)
    private String username;

    @Column(name = "email", nullable = false, length = 120)
    private String email;

    /**
     * BCrypt-hashed password. Never expose this field in DTOs.
     */
    @Column(name = "password", nullable = false)
    @com.fasterxml.jackson.annotation.JsonIgnore
    private String password;

    @Column(name = "full_name", nullable = false, length = 150)
    private String fullName;

    @Column(name = "phone_number", length = 20)
    private String phoneNumber;

    @Builder.Default
    @Column(name = "is_active", nullable = false)
    private Boolean isActive = true;

    /**
     * LAZY: roles are fetched only when explicitly accessed.
     * CascadeType is intentionally omitted — roles are pre-seeded reference data
     * and must NEVER be cascaded from User operations.
     */
    @ManyToMany(fetch = FetchType.LAZY)
    @JoinTable(
        name = "user_roles",
        joinColumns        = @JoinColumn(name = "user_id",  referencedColumnName = "id"),
        inverseJoinColumns = @JoinColumn(name = "role_id",  referencedColumnName = "id")
    )
    @Builder.Default
    @com.fasterxml.jackson.annotation.JsonIgnore
    private Set<Role> roles = new HashSet<>();

    // ── Helper Methods ────────────────────────────────────────────────────

    public void addRole(Role role) {
        this.roles.add(role);
    }
}
