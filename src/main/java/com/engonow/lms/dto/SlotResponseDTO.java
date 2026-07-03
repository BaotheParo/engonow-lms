package com.engonow.lms.dto;

import java.time.LocalDate;
import java.time.LocalTime;

public record SlotResponseDTO(
    Long id,
    Long tutorId,
    String tutorName,
    LocalDate slotDate,
    LocalTime startTime,
    LocalTime endTime,
    String slotStatus
) {}
