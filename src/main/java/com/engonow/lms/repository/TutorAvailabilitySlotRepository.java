package com.engonow.lms.repository;

import com.engonow.lms.entity.TutorAvailabilitySlot;
import com.engonow.lms.enums.SlotStatus;
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

@Repository
public interface TutorAvailabilitySlotRepository extends JpaRepository<TutorAvailabilitySlot, Long> {

    /**
     * Public-facing: list available slots without exposing teacher identity.
     * Returns only future AVAILABLE slots, ordered chronologically.
     */
    @Query("""
           SELECT s FROM TutorAvailabilitySlot s
           WHERE s.status = 'AVAILABLE'
             AND s.startTime > :now
           ORDER BY s.startTime ASC
           """)
    List<TutorAvailabilitySlot> findPublicAvailableSlots(@Param("now") LocalDateTime now);

    /**
     * Used by the booking service. Applies PESSIMISTIC_WRITE lock as a fallback
     * safety net to complement @Version Optimistic Locking when fetching the slot
     * right before booking.
     *
     * Rationale for PESSIMISTIC_WRITE here alongside @Version:
     *   - @Version (optimistic) handles the common low-contention case.
     *   - This @Lock(PESSIMISTIC_WRITE) query is used WITHIN the transaction that
     *     performs the actual status update, guaranteeing serialization for that
     *     specific fetch-then-update sequence during the critical booking window.
     *
     * This is a "belt-and-suspenders" approach for a mission-critical booking path.
     */
    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("SELECT s FROM TutorAvailabilitySlot s WHERE s.id = :id AND s.status = 'AVAILABLE'")
    Optional<TutorAvailabilitySlot> findAvailableByIdForUpdate(@Param("id") Long id);

    List<TutorAvailabilitySlot> findByTeacherIdAndStatus(Long teacherId, SlotStatus status);

    List<TutorAvailabilitySlot> findByTeacherIdAndStartTimeBetween(
        Long teacherId, LocalDateTime from, LocalDateTime to);
}
