package com.engonow.lms.entity;

import com.engonow.lms.enums.RoleName;
import jakarta.persistence.*;
import lombok.*;

/**
 * Represents an application role (ROLE_STUDENT, ROLE_TEACHER, ROLE_ADMIN).
 *
 * Design notes:
 *  - Stored as a small lookup/reference table seeded on startup (see DataSeeder).
 *  - @Enumerated(EnumType.STRING): stores human-readable string in DB instead of
 *    fragile ordinal integers.
 *  - No @OneToMany back-reference to Users here to avoid bidirectional complexity;
 *    navigation is always User → Roles.
 */
@Entity
@Table(name = "roles",
       uniqueConstraints = @UniqueConstraint(name = "uk_role_name", columnNames = "name"))
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class Role {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Enumerated(EnumType.STRING)
    @Column(name = "name", nullable = false, length = 30)
    private RoleName name;
}
