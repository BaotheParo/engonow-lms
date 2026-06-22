package com.engonow.lms.enums;

/**
 * Application-level roles enforced by Spring Security.
 * Prefix "ROLE_" is the Spring Security naming convention required
 * for hasRole() / @PreAuthorize("hasRole('ADMIN')") to work correctly.
 */
public enum RoleName {
    ROLE_STUDENT,
    ROLE_TEACHER,
    ROLE_ADMIN
}
