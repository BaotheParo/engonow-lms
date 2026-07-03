package com.engonow.lms.controller;

import com.engonow.lms.dto.BookingRequestDTO;
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
        
        bookingService.createBooking(requestDTO);
        
        log.info("[BOOKING CONTROLLER] Booking request processed successfully for slotId={}, studentId={}",
                requestDTO.slotId(), requestDTO.studentId());
        
        return ResponseEntity.status(HttpStatus.CREATED).body("Booking request initiated successfully");
    }
}
