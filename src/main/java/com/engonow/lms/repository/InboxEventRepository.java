package com.engonow.lms.repository;

import com.engonow.lms.entity.InboxEvent;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.Optional;
import java.util.UUID;

@Repository
public interface InboxEventRepository extends JpaRepository<InboxEvent, UUID> {

    Optional<InboxEvent> findByIdempotencyKey(UUID idempotencyKey);

    @Modifying(clearAutomatically = true)
    @Query(value = """
        INSERT INTO inbox_events (id, event_id, idempotency_key, event_type, source_service, payload, status, processed_at)
        VALUES (gen_random_uuid(), :eventId, :idempotencyKey, :eventType, :sourceService, CAST(:payload AS jsonb), 'PROCESSED', CURRENT_TIMESTAMP)
        ON CONFLICT (idempotency_key) DO NOTHING
        """, nativeQuery = true)
    int tryAcquireInbox(
        @Param("eventId") UUID eventId,
        @Param("idempotencyKey") UUID idempotencyKey,
        @Param("eventType") String eventType,
        @Param("sourceService") String sourceService,
        @Param("payload") String payload
    );
}
