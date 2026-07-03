package com.engonow.lms.service;

import com.engonow.lms.dto.SlotResponseDTO;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

import java.time.LocalDate;

public interface TutorAvailabilitySlotService {
    Page<SlotResponseDTO> getAvailableSlots(LocalDate startDate, LocalDate endDate, Long tutorId, Pageable pageable);
}
