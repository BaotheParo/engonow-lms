package com.engonow.lms.repository;

import com.engonow.lms.entity.SpeakingSessionResult;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.Optional;

@Repository
public interface SpeakingSessionResultRepository extends JpaRepository<SpeakingSessionResult, Long> {

    /**
     * Idempotency check: if we've already processed this sessionId, skip re-processing.
     */
    Optional<SpeakingSessionResult> findBySessionId(String sessionId);

    Optional<SpeakingSessionResult> findByBookingId(Long bookingId);
}
