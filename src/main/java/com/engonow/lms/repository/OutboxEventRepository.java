package com.engonow.lms.repository;

import com.engonow.lms.entity.OutboxEvent;
import com.engonow.lms.enums.OutboxStatus;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

@Repository
public interface OutboxEventRepository extends JpaRepository<OutboxEvent, UUID> {

    long countByStatus(OutboxStatus status);

    List<OutboxEvent> findTop100ByStatusOrderByCreatedAtAsc(OutboxStatus status);

    List<OutboxEvent> findByStatusAndRetryCountLessThan(OutboxStatus status, int maxRetries);

    @Query(value = "SELECT * FROM outbox_events WHERE status = 'PENDING' AND created_at < :threshold ORDER BY created_at ASC LIMIT :limit FOR UPDATE SKIP LOCKED", nativeQuery = true)
    List<OutboxEvent> findPendingEventsForReconciliation(
        @Param("threshold") Instant threshold,
        @Param("limit") int limit
    );

    @Modifying
    @Query("DELETE FROM OutboxEvent o WHERE o.status = :status AND o.publishedAt < :threshold")
    int deleteByStatusAndPublishedAtBefore(
        @Param("status") OutboxStatus status,
        @Param("threshold") Instant threshold
    );
}
