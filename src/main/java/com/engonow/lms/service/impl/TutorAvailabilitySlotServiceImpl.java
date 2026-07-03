package com.engonow.lms.service.impl;

import com.engonow.lms.dto.SlotResponseDTO;
import com.engonow.lms.mapper.SlotMapper;
import com.engonow.lms.repository.TutorAvailabilitySlotRepository;
import com.engonow.lms.service.TutorAvailabilitySlotService;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDate;

@Service
@RequiredArgsConstructor
public class TutorAvailabilitySlotServiceImpl implements TutorAvailabilitySlotService {

    private final TutorAvailabilitySlotRepository slotRepository;
    private final SlotMapper slotMapper;

    @Override
    @Transactional(readOnly = true)
    public Page<SlotResponseDTO> getAvailableSlots(LocalDate startDate, LocalDate endDate, Long tutorId, Pageable pageable) {
        return slotRepository.findAvailableSlots(tutorId, startDate, endDate, pageable)
                .map(slotMapper::toDTO);
    }
}
