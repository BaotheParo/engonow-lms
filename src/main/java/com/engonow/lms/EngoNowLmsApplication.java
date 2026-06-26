package com.engonow.lms;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

/**
 * ENGONOW Smart LMS – Spring Boot Entry Point
 *
 * Key architectural decisions documented here for onboarding:
 *
 *  1. open-in-view=false (application.yml): Transactions are strictly bounded
 *     to the service layer. Any attempt to lazy-load entities in the controller
 *     or view will throw LazyInitializationException — this is intentional; it
 *     forces developers to load data properly in service queries.
 *
 *  2. @EnableJpaAuditing in JpaAuditingConfig: Populates @CreatedDate /
 *     @LastModifiedDate on all entities extending BaseEntity.
 *
 *  3. @EnableAsync in AsyncConfig: Activates Spring's proxy-based @Async
 *     method interception. Methods annotated with @Async in @Service beans
 *     run on the configured ThreadPoolTaskExecutor.
 *
 *  4. MapStruct (mapstruct.defaultComponentModel=spring): All generated mapper
 *     implementations are Spring @Component beans, injectable via @Autowired.
 */
@SpringBootApplication
public class EngoNowLmsApplication {

    public static void main(String[] args) {
        SpringApplication.run(EngoNowLmsApplication.class, args);
    }

    @Bean
    public CommandLineRunner seedData(DatabaseSeeder seeder) {
        return args -> seeder.seed();
    }
}
