package com.engonow.lms.service.impl;

import com.engonow.lms.dto.BookingRequestDTO;
import com.engonow.lms.entity.MockTestBooking;
import com.engonow.lms.entity.TutorAvailabilitySlot;
import com.engonow.lms.entity.User;
import com.engonow.lms.enums.BookingStatus;
import com.engonow.lms.enums.SlotStatus;
import com.engonow.lms.exception.SlotNotAvailableException;
import com.engonow.lms.repository.MockTestBookingRepository;
import com.engonow.lms.repository.TutorAvailabilitySlotRepository;
import com.engonow.lms.repository.UserRepository;
import com.engonow.lms.service.BookingService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
@Slf4j
public class BookingServiceImpl implements BookingService {

    private final MockTestBookingRepository mockTestBookingRepository;
    private final TutorAvailabilitySlotRepository tutorAvailabilitySlotRepository;
    private final UserRepository userRepository;

    @Override
    @Transactional
    public void createBooking(BookingRequestDTO dto) {
        log.info("Initiating booking process for slot ID: {} and student ID: {}", dto.slotId(), dto.studentId());

        TutorAvailabilitySlot slot = tutorAvailabilitySlotRepository.findByIdForUpdate(dto.slotId())
                .orElseThrow(() -> new IllegalArgumentException("Target tutor availability slot not found"));

        if (slot.getSlotStatus() != SlotStatus.AVAILABLE) {
            log.warn("Booking failed: Tutor availability slot {} status is {}", dto.slotId(), slot.getSlotStatus());
            throw new SlotNotAvailableException("The selected slot is no longer available for booking");
        }

        User student = userRepository.findById(dto.studentId())
                .orElseThrow(() -> new IllegalArgumentException("Student user entity not found"));

        slot.setSlotStatus(SlotStatus.BOOKED);
        tutorAvailabilitySlotRepository.save(slot);

        MockTestBooking booking = MockTestBooking.builder()
                .student(student)
                .slot(slot)
                .bookingStatus(BookingStatus.CONFIRMED)
                .notes(dto.notes())
                .build();

        mockTestBookingRepository.save(booking);

        log.info("Successfully created booking for slot ID: {} and student ID: {}", dto.slotId(), dto.studentId());
    }
}
