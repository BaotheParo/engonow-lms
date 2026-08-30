package com.engonow.lms.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

import java.util.concurrent.Executor;

/**
 * Configures the @Async thread pool used for:
 *  - Email confirmation sending (BookingService)
 *  - Cloudinary image uploads (SubmissionService)
 *
 * Why a custom Executor instead of the default SimpleAsyncTaskExecutor?
 *  - SimpleAsyncTaskExecutor spawns a new thread per task — no pooling, no limits.
 *  - ThreadPoolTaskExecutor has configurable core/max pool sizes and a bounded queue,
 *    preventing resource exhaustion under high load.
 *
 * Thread naming (engonow-async-N) makes async threads identifiable in logs/profilers.
 */
@Configuration
@EnableAsync
public class AsyncConfig {

    @Bean(name = "taskExecutor")
    public Executor taskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(16);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("engonow-async-");
        // Caller runs rejected tasks on the calling thread (graceful degradation)
        executor.setRejectedExecutionHandler(new java.util.concurrent.ThreadPoolExecutor.CallerRunsPolicy());
        executor.initialize();
        return executor;
    }

    /**
     * Dedicated ThreadPoolTaskScheduler for @Scheduled tasks (SSE heartbeat pings, outbox polling).
     * Prevents single-threaded scheduler bottleneck under high concurrent SSE subscribers.
     */
    @Bean(name = "taskScheduler")
    public org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler taskScheduler() {
        org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler scheduler =
            new org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler();
        scheduler.setPoolSize(8);
        scheduler.setThreadNamePrefix("engonow-scheduled-");
        scheduler.setWaitForTasksToCompleteOnShutdown(true);
        scheduler.setAwaitTerminationSeconds(30);
        scheduler.setRejectedExecutionHandler(new java.util.concurrent.ThreadPoolExecutor.CallerRunsPolicy());
        scheduler.initialize();
        return scheduler;
    }
}
