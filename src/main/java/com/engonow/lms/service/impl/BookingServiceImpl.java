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
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
public class BookingServiceImpl implements BookingService {

    private final TutorAvailabilitySlotRepository slotRepository;
    private final MockTestBookingRepository bookingRepository;
    private final UserRepository userRepository;

    @Override
    @Transactional
    public MockTestBooking createBooking(BookingRequestDTO requestDTO) {
        TutorAvailabilitySlot slot = slotRepository.findByIdForUpdate(requestDTO.slotId())
                .orElseThrow(() -> new IllegalArgumentException("TutorAvailabilitySlot not found for ID: " + requestDTO.slotId()));

        if (slot.getSlotStatus() != SlotStatus.AVAILABLE) {
            throw new SlotNotAvailableException("Slot is not available: " + requestDTO.slotId());
        }

        User student = userRepository.findById(requestDTO.studentId())
                .orElseThrow(() -> new IllegalArgumentException("User not found for ID: " + requestDTO.studentId()));

        slot.setSlotStatus(SlotStatus.BOOKED);
        slotRepository.save(slot);

        MockTestBooking booking = MockTestBooking.builder()
                .student(student)
                .slot(slot)
                .bookingStatus(BookingStatus.CONFIRMED)
                .notes(requestDTO.notes())
                .build();

        return bookingRepository.save(booking);
    }
}
