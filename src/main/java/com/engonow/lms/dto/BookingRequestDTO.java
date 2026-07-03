package com.engonow.lms.dto;

import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record BookingRequestDTO(
    @NotNull(message = "Slot ID must not be null") Long slotId,
    @NotNull(message = "Student ID must not be null") Long studentId,
    @Size(max = 500, message = "Notes must not exceed 500 characters") String notes
) {}
