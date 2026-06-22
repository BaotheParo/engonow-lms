package com.engonow.lms.entity;

import com.engonow.lms.enums.SlotStatus;
import jakarta.persistence.*;
import lombok.*;

import java.time.LocalDateTime;

/**
 * Represents a time window that a Teacher/Tutor has declared as available
 * for a 1-on-1 Speaking Mock Test.
 *
 * ─────────────────────────────────────────────────────────────────────────────
 * CONCURRENCY STRATEGY — Optimistic Locking via @Version
 * ─────────────────────────────────────────────────────────────────────────────
 * Problem: Two students simultaneously request the same slot.
 *   T1: SELECT slot WHERE id=5 → status=AVAILABLE, version=0
 *   T2: SELECT slot WHERE id=5 → status=AVAILABLE, version=0
 *   T1: UPDATE slots SET status='BOOKED', version=1 WHERE id=5 AND version=0 ✓
 *   T2: UPDATE slots SET status='BOOKED', version=1 WHERE id=5 AND version=0 ✗
 *       → 0 rows affected → Hibernate throws OptimisticLockException
 *
 * The service layer catches OptimisticLockException and returns HTTP 409 Conflict.
 * This is preferred over Pessimistic Locking for this use case because:
 *   1. Booking contention is LOW (rare for same slot).
 *   2. Pessimistic locks hold DB row-locks across network round trips, risking deadlocks.
 *   3. Optimistic locking is non-blocking until the final UPDATE.
 *
 * @Version field MUST be of type Integer/Long (primitives also work but boxed is safer
 * as they can represent null for new, unversioned entities loaded from legacy data).
 * ─────────────────────────────────────────────────────────────────────────────
 */
@Entity
@Table(name = "tutor_availability_slots",
       indexes = {
           @Index(name = "idx_slot_teacher_status", columnList = "teacher_id, status"),
           @Index(name = "idx_slot_start_time",     columnList = "start_time")
       })
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class TutorAvailabilitySlot extends BaseEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    /**
     * Optimistic lock version column.
     * Hibernate automatically increments this on every UPDATE and checks it in the WHERE clause.
     */
    @Version
    @Column(name = "version", nullable = false)
    private Integer version;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "teacher_id", nullable = false,
                foreignKey = @ForeignKey(name = "fk_slot_teacher"))
    private User teacher;

    @Column(name = "start_time", nullable = false)
    private LocalDateTime startTime;

    @Column(name = "end_time", nullable = false)
    private LocalDateTime endTime;

    @Builder.Default
    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 20)
    private SlotStatus status = SlotStatus.AVAILABLE;

    @Column(name = "notes", length = 500)
    private String notes;

    // ── Helper Methods ────────────────────────────────────────────────────

    public boolean isAvailable() {
        return SlotStatus.AVAILABLE.equals(this.status);
    }

    public void book() {
        this.status = SlotStatus.BOOKED;
    }

    public void cancel() {
        this.status = SlotStatus.AVAILABLE;
    }
}
