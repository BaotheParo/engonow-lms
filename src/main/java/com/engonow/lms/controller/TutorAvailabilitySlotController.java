package com.engonow.lms.controller;

import com.engonow.lms.dto.SlotResponseDTO;
import com.engonow.lms.service.TutorAvailabilitySlotService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.time.LocalDate;

@RestController
@RequestMapping("/api/v1/slots")
@RequiredArgsConstructor
@Slf4j
public class TutorAvailabilitySlotController {

    private final TutorAvailabilitySlotService slotService;

    @GetMapping("/available")
    public ResponseEntity<Page<SlotResponseDTO>> getAvailableSlots(
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate startDate,
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate endDate,
            @RequestParam(required = false) Long tutorId,
            Pageable pageable) {

        log.info("[SLOT CONTROLLER] Requesting available slots: startDate={}, endDate={}, tutorId={}, pageable={}",
                startDate, endDate, tutorId, pageable);

        Page<SlotResponseDTO> availableSlots = slotService.getAvailableSlots(startDate, endDate, tutorId, pageable);

        log.info("[SLOT CONTROLLER] Returning {} available slots", availableSlots.getNumberOfElements());
        return ResponseEntity.ok(availableSlots);
    }
}
