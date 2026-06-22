package com.engonow.lms.entity;

import com.engonow.lms.enums.BookingStatus;
import jakarta.persistence.*;
import lombok.*;

/**
 * Records a Student's confirmed booking of a TutorAvailabilitySlot.
 *
 * Design notes:
 *  - Both student and slot are LAZY @ManyToOne references.
 *    The booking list page only needs student name + slot time, loaded via projection.
 *
 *  - @OneToOne(mappedBy) link to SpeakingSessionResult: a booking eventually
 *    produces a result but NOT immediately. Optional=true is implicit on the inverse side.
 *
 *  - The unique constraint on slot_id ensures DB-level enforcement that one slot
 *    cannot appear in two confirmed bookings (belt-and-suspenders alongside @Version).
 */
@Entity
@Table(name = "mock_test_bookings",
       uniqueConstraints = @UniqueConstraint(
           name = "uk_booking_slot",
           columnNames = "slot_id"
       ),
       indexes = {
           @Index(name = "idx_booking_student", columnList = "student_id"),
           @Index(name = "idx_booking_status",  columnList = "status")
       })
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class MockTestBooking extends BaseEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "student_id", nullable = false,
                foreignKey = @ForeignKey(name = "fk_booking_student"))
    private User student;

    /**
     * The slot being booked. Unique constraint prevents double-booking at DB level.
     * @Version on TutorAvailabilitySlot prevents race conditions at application level.
     */
    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "slot_id", nullable = false,
                foreignKey = @ForeignKey(name = "fk_booking_slot"))
    private TutorAvailabilitySlot slot;

    @Builder.Default
    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 20)
    private BookingStatus status = BookingStatus.CONFIRMED;

    @Column(name = "student_notes", length = 500)
    private String studentNotes;

    /**
     * Inverse side of the @OneToOne with SpeakingSessionResult.
     * Populated later when AI grading completes via webhook.
     */
    @OneToOne(mappedBy = "booking", fetch = FetchType.LAZY)
    private SpeakingSessionResult speakingResult;
}
