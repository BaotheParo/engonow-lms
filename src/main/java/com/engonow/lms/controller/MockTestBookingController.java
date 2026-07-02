package com.engonow.lms.controller;

import com.engonow.lms.dto.BookingRequestDTO;
import com.engonow.lms.entity.MockTestBooking;
import com.engonow.lms.exception.SlotNotAvailableException;
import com.engonow.lms.service.BookingService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/bookings")
@RequiredArgsConstructor
public class MockTestBookingController {

    private final BookingService bookingService;

    @PostMapping
    public ResponseEntity<MockTestBooking> createBooking(@Valid @RequestBody BookingRequestDTO requestDTO) {
        MockTestBooking booking = bookingService.createBooking(requestDTO);
        return ResponseEntity.ok(booking);
    }

    @ExceptionHandler(SlotNotAvailableException.class)
    public ResponseEntity<ErrorResponse> handleSlotNotAvailable(SlotNotAvailableException ex) {
        return ResponseEntity.status(HttpStatus.BAD_REQUEST)
                .body(new ErrorResponse(ex.getMessage(), "SLOT_NOT_AVAILABLE"));
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<ErrorResponse> handleIllegalArgument(IllegalArgumentException ex) {
        return ResponseEntity.status(HttpStatus.BAD_REQUEST)
                .body(new ErrorResponse(ex.getMessage(), "INVALID_ARGUMENT"));
    }

    @ExceptionHandler(IllegalStateException.class)
    public ResponseEntity<ErrorResponse> handleIllegalState(IllegalStateException ex) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(new ErrorResponse(ex.getMessage(), "CONFLICT"));
    }

    public record ErrorResponse(String message, String error) {}
}
