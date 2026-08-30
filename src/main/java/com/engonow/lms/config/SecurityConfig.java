package com.engonow.lms.config;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.AccessDeniedHandler;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

@Configuration
@EnableWebSecurity
@EnableMethodSecurity(prePostEnabled = true)
@RequiredArgsConstructor
@Slf4j
public class SecurityConfig {

    @Bean
    public SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .csrf(AbstractHttpConfigurer::disable)
            .cors(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .exceptionHandling(exceptions -> exceptions
                .authenticationEntryPoint(customAuthenticationEntryPoint())
                .accessDeniedHandler(customAccessDeniedHandler())
            )
            .authorizeHttpRequests(auth -> auth
                // Public observability, health & documentation endpoints
                .requestMatchers(
                    "/health",
                    "/actuator/health",
                    "/actuator/prometheus",
                    "/v3/api-docs/**",
                    "/swagger-ui/**",
                    "/swagger-ui.html",
                    "/api/v1/callback/**",
                    "/api/v1/writing/webhook/**"
                ).permitAll()
                // Strict Admin & Calibration endpoints
                .requestMatchers(
                    "/api/v1/admin/**",
                    "/api/v1/admin/calibration/**"
                ).hasRole("ADMIN")
                // All student submission & evaluation endpoints require authentication
                .requestMatchers(
                    "/api/v1/writing/**",
                    "/api/v1/writing-submissions/**",
                    "/api/v1/speaking/**",
                    "/api/v1/speaking-submissions/**"
                ).authenticated()
                .anyRequest().authenticated()
            )
            .addFilterBefore(new MockJwtAuthenticationFilter(), UsernamePasswordAuthenticationFilter.class);

        return http.build();
    }

    @Bean
    public AuthenticationEntryPoint customAuthenticationEntryPoint() {
        return (request, response, authException) -> {
            log.warn("[SECURITY 401] Unauthorized access attempt to {}: {}",
                request.getRequestURI(), authException.getMessage());
            response.setStatus(HttpStatus.UNAUTHORIZED.value());
            response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            response.getWriter().write(
                "{\"error\":\"Unauthorized\",\"message\":\"Authentication required to access this resource\",\"status\":401}"
            );
        };
    }

    @Bean
    public AccessDeniedHandler customAccessDeniedHandler() {
        return (request, response, accessDeniedException) -> {
            log.warn("[SECURITY 403] Forbidden access attempt to {}: {}",
                request.getRequestURI(), accessDeniedException.getMessage());
            response.setStatus(HttpStatus.FORBIDDEN.value());
            response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            response.getWriter().write(
                "{\"error\":\"Forbidden\",\"message\":\"Access denied: Insufficient privileges\",\"status\":403}"
            );
        };
    }

    /**
     * Stateless authentication filter supporting Bearer tokens and testing headers (X-User-Id, X-User-Role).
     */
    public static class MockJwtAuthenticationFilter extends OncePerRequestFilter {
        @Override
        protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain
        ) throws ServletException, IOException {
            String authHeader = request.getHeader("Authorization");
            String roleHeader = request.getHeader("X-User-Role");
            String userIdHeader = request.getHeader("X-User-Id");

            if (authHeader != null && authHeader.startsWith("Bearer ")) {
                String token = authHeader.substring(7).trim();
                List<GrantedAuthority> authorities = new ArrayList<>();
                String principal = userIdHeader != null ? userIdHeader : "user";

                if (token.contains("admin") || "ROLE_ADMIN".equalsIgnoreCase(roleHeader) || "ADMIN".equalsIgnoreCase(roleHeader)) {
                    authorities.add(new SimpleGrantedAuthority("ROLE_ADMIN"));
                    authorities.add(new SimpleGrantedAuthority("ROLE_STUDENT"));
                    principal = userIdHeader != null ? userIdHeader : "admin";
                } else {
                    authorities.add(new SimpleGrantedAuthority("ROLE_STUDENT"));
                }

                UsernamePasswordAuthenticationToken auth =
                    new UsernamePasswordAuthenticationToken(principal, token, authorities);
                SecurityContextHolder.getContext().setAuthentication(auth);
            } else if (roleHeader != null) {
                List<GrantedAuthority> authorities = new ArrayList<>();
                String principal = userIdHeader != null ? userIdHeader : "user";

                if ("ROLE_ADMIN".equalsIgnoreCase(roleHeader) || "ADMIN".equalsIgnoreCase(roleHeader)) {
                    authorities.add(new SimpleGrantedAuthority("ROLE_ADMIN"));
                    authorities.add(new SimpleGrantedAuthority("ROLE_STUDENT"));
                    principal = userIdHeader != null ? userIdHeader : "admin";
                } else {
                    authorities.add(new SimpleGrantedAuthority("ROLE_STUDENT"));
                }

                UsernamePasswordAuthenticationToken auth =
                    new UsernamePasswordAuthenticationToken(principal, null, authorities);
                SecurityContextHolder.getContext().setAuthentication(auth);
            }

            filterChain.doFilter(request, response);
        }
    }
}
