package com.engonow.lms.repository;

import com.engonow.lms.entity.TutorAvailabilitySlot;
import com.engonow.lms.enums.SlotStatus;
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.time.LocalDate;
import java.time.LocalTime;
import java.util.List;
import java.util.Optional;

@Repository
public interface TutorAvailabilitySlotRepository extends JpaRepository<TutorAvailabilitySlot, Long> {

    @Query("""
           SELECT s FROM TutorAvailabilitySlot s
           WHERE s.slotStatus = 'AVAILABLE'
             AND s.slotDate >= :today
           ORDER BY s.slotDate ASC, s.startTime ASC
           """)
    List<TutorAvailabilitySlot> findPublicAvailableSlots(@Param("today") LocalDate today);

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("SELECT s FROM TutorAvailabilitySlot s WHERE s.id = :id AND s.slotStatus = 'AVAILABLE'")
    Optional<TutorAvailabilitySlot> findAvailableByIdForUpdate(@Param("id") Long id);

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("SELECT s FROM TutorAvailabilitySlot s WHERE s.id = :id")
    Optional<TutorAvailabilitySlot> findByIdForUpdate(@Param("id") Long id);

    List<TutorAvailabilitySlot> findByTutorIdAndSlotStatus(Long tutorId, SlotStatus slotStatus);

    List<TutorAvailabilitySlot> findByTutorIdAndSlotDateAndStartTimeBetween(
        Long tutorId, LocalDate slotDate, LocalTime from, LocalTime to);
}
