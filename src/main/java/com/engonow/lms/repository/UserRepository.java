package com.engonow.lms.repository;

import com.engonow.lms.entity.User;
import com.engonow.lms.enums.RoleName;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.Optional;

@Repository
public interface UserRepository extends JpaRepository<User, Long> {

    Optional<User> findByUsername(String username);

    Optional<User> findByEmail(String email);

    boolean existsByUsername(String username);

    boolean existsByEmail(String email);

    /**
     * JOIN FETCH roles to avoid N+1 when loading a User for authentication.
     * Spring Security's UserDetailsService calls this; roles MUST be loaded eagerly
     * in the same query to avoid LazyInitializationException outside the session.
     */
    @Query("SELECT u FROM User u JOIN FETCH u.roles WHERE u.username = :username")
    Optional<User> findByUsernameWithRoles(@Param("username") String username);

    /**
     * Find all active users with a specific role (used for teacher lookup).
     */
    @Query("""
           SELECT u FROM User u
           JOIN u.roles r
           WHERE r.name = :roleName
             AND u.isActive = true
           """)
    java.util.List<User> findActiveUsersByRole(@Param("roleName") RoleName roleName);
}
