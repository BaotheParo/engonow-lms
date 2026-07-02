package com.engonow.lms.entity;

import com.engonow.lms.enums.BookingStatus;
import jakarta.persistence.*;
import lombok.*;

@Entity
@Table(
    name = "mock_test_bookings",
    uniqueConstraints = @UniqueConstraint(name = "uk_booking_slot_id", columnNames = "slot_id")
)
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
@com.fasterxml.jackson.annotation.JsonIgnoreProperties({"hibernateLazyInitializer", "handler"})
public class MockTestBooking extends BaseEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "student_id", nullable = false)
    private User student;

    @OneToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "slot_id", nullable = false)
    private TutorAvailabilitySlot slot;

    @Enumerated(EnumType.STRING)
    @Column(name = "booking_status", nullable = false, length = 20)
    private BookingStatus bookingStatus;

    @Column(name = "notes", columnDefinition = "TEXT")
    private String notes;

    @OneToOne(mappedBy = "booking", fetch = FetchType.LAZY)
    private SpeakingSessionResult speakingResult;
}
