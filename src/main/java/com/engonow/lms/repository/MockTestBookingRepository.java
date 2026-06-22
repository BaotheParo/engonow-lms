package com.engonow.lms.repository;

import com.engonow.lms.entity.MockTestBooking;
import com.engonow.lms.enums.BookingStatus;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

@Repository
public interface MockTestBookingRepository extends JpaRepository<MockTestBooking, Long> {

    /**
     * JOIN FETCH student + slot + teacher in a single query.
     * Used when loading booking detail for email confirmation.
     */
    @Query("""
           SELECT b FROM MockTestBooking b
           JOIN FETCH b.student s
           JOIN FETCH b.slot sl
           JOIN FETCH sl.teacher t
           WHERE b.id = :bookingId
           """)
    Optional<MockTestBooking> findByIdWithDetails(@Param("bookingId") Long bookingId);

    @Query("""
           SELECT b FROM MockTestBooking b
           JOIN FETCH b.slot sl
           WHERE b.student.id = :studentId
           ORDER BY sl.startTime DESC
           """)
    List<MockTestBooking> findByStudentIdWithSlots(@Param("studentId") Long studentId);

    boolean existsBySlotIdAndStatus(Long slotId, BookingStatus status);
}
