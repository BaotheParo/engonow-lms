package com.engonow.lms.controller;

import com.engonow.lms.dto.BookingRequestDTO;
import com.engonow.lms.exception.SlotNotAvailableException;
import com.engonow.lms.service.BookingService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/bookings")
@RequiredArgsConstructor
@Slf4j
public class MockTestBookingController {

    private final BookingService bookingService;

    @PostMapping
    public ResponseEntity<String> createBooking(@Valid @RequestBody BookingRequestDTO requestDTO) {
        log.info("[BOOKING CONTROLLER] Initiating booking request validation for slotId={}, studentId={}",
                requestDTO.slotId(), requestDTO.studentId());

        try {
            bookingService.createBooking(requestDTO);
            log.info("[BOOKING CONTROLLER] Booking request processed successfully for slotId={}, studentId={}",
                    requestDTO.slotId(), requestDTO.studentId());
            return ResponseEntity.status(HttpStatus.CREATED).body("Booking request initiated successfully");
        } catch (SlotNotAvailableException ex) {
            log.warn("[BOOKING CONTROLLER] Booking failed because slot was not available: {}", ex.getMessage());
            throw ex;
        } catch (IllegalArgumentException ex) {
            log.error("[BOOKING CONTROLLER] Booking failed due to invalid arguments: {}", ex.getMessage());
            throw ex;
        } catch (IllegalStateException ex) {
            log.error("[BOOKING CONTROLLER] Booking failed due to conflict state: {}", ex.getMessage());
            throw ex;
        }
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
