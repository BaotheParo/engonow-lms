package com.engonow.lms.dto;

import jakarta.validation.constraints.NotNull;

public record BookingRequestDTO(
    @NotNull(message = "Slot ID must not be null") Long slotId,
    @NotNull(message = "Student ID must not be null") Long studentId,
    String notes
) {}
