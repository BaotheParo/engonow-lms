package com.engonow.lms.controller;

import com.engonow.lms.dto.BookingRequestDTO;
import com.engonow.lms.entity.MockTestBooking;
import com.engonow.lms.entity.TutorAvailabilitySlot;
import com.engonow.lms.entity.User;
import com.engonow.lms.enums.BookingStatus;
import com.engonow.lms.enums.SlotStatus;
import com.engonow.lms.repository.MockTestBookingRepository;
import com.engonow.lms.repository.TutorAvailabilitySlotRepository;
import com.engonow.lms.repository.UserRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.time.LocalDate;
import java.time.LocalTime;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.*;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
public class MockTestBookingControllerIT {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private TutorAvailabilitySlotRepository slotRepository;

    @Autowired
    private MockTestBookingRepository bookingRepository;

    private User student;
    private User tutor;
    private TutorAvailabilitySlot availableSlot;
    private TutorAvailabilitySlot bookedSlot;

    @BeforeEach
    public void setUp() {
        // Clean state
        bookingRepository.deleteAllInBatch();
        slotRepository.deleteAllInBatch();
        userRepository.deleteAllInBatch();

        // Create Users
        tutor = User.builder()
                .username("tutor_test")
                .email("tutor_test@engonow.com")
                .password("$2a$10$P7X1Y9j2m.Y4kO.6v.hUde5JzG5H8N9l3v/H2j8q8V9v8j6H8N9l3")
                .fullName("Tutor Test")
                .phoneNumber("0987654322")
                .isActive(true)
                .build();
        tutor = userRepository.save(tutor);

        student = User.builder()
                .username("student_test")
                .email("student_test@engonow.com")
                .password("$2a$10$P7X1Y9j2m.Y4kO.6v.hUde5JzG5H8N9l3v/H2j8q8V9v8j6H8N9l3")
                .fullName("Student Test")
                .phoneNumber("0912345679")
                .isActive(true)
                .build();
        student = userRepository.save(student);

        // Create Available Slot
        availableSlot = TutorAvailabilitySlot.builder()
                .tutor(tutor)
                .slotDate(LocalDate.now().plusDays(2))
                .startTime(LocalTime.of(10, 0))
                .endTime(LocalTime.of(11, 0))
                .slotStatus(SlotStatus.AVAILABLE)
                .build();
        availableSlot = slotRepository.save(availableSlot);

        // Create Booked Slot
        bookedSlot = TutorAvailabilitySlot.builder()
                .tutor(tutor)
                .slotDate(LocalDate.now().plusDays(2))
                .startTime(LocalTime.of(11, 0))
                .endTime(LocalTime.of(12, 0))
                .slotStatus(SlotStatus.BOOKED)
                .build();
        bookedSlot = slotRepository.save(bookedSlot);
    }

    @AfterEach
    public void cleanUp() {
        bookingRepository.deleteAllInBatch();
        slotRepository.deleteAllInBatch();
        userRepository.deleteAllInBatch();
    }

    @Test
    public void testCreateBooking_Success() throws Exception {
        BookingRequestDTO requestDTO = new BookingRequestDTO(
                availableSlot.getId(),
                student.getId(),
                "Please focus on my fluency and pausing."
        );

        mockMvc.perform(post("/api/v1/bookings")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(requestDTO)))
                .andExpect(status().isCreated());

        // Verify slot state transition
        TutorAvailabilitySlot updatedSlot = slotRepository.findById(availableSlot.getId())
                .orElseThrow(() -> new AssertionError("Slot should exist"));
        assertEquals(SlotStatus.BOOKED, updatedSlot.getSlotStatus());

        // Verify booking entry creation
        List<MockTestBooking> bookings = bookingRepository.findByStudentId(student.getId());
        assertEquals(1, bookings.size());
        MockTestBooking booking = bookings.get(0);
        assertEquals(BookingStatus.CONFIRMED, booking.getBookingStatus());
        assertEquals("Please focus on my fluency and pausing.", booking.getNotes());
        assertEquals(availableSlot.getId(), booking.getSlot().getId());
    }

    @Test
    public void testCreateBooking_Conflict_AlreadyBooked() throws Exception {
        BookingRequestDTO requestDTO = new BookingRequestDTO(
                bookedSlot.getId(),
                student.getId(),
                "Attempting to book an unavailable slot."
        );

        mockMvc.perform(post("/api/v1/bookings")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(requestDTO)))
                .andExpect(status().isBadRequest());

        // Verify slot state remains unchanged
        TutorAvailabilitySlot updatedSlot = slotRepository.findById(bookedSlot.getId())
                .orElseThrow(() -> new AssertionError("Slot should exist"));
        assertEquals(SlotStatus.BOOKED, updatedSlot.getSlotStatus());

        // Verify no booking was created
        List<MockTestBooking> bookings = bookingRepository.findByStudentId(student.getId());
        assertTrue(bookings.isEmpty());
    }

    @Test
    public void testCreateBooking_Concurrency_PessimisticLocking() throws Exception {
        int threadCount = 8;
        ExecutorService executorService = Executors.newFixedThreadPool(threadCount);
        CountDownLatch startLatch = new CountDownLatch(1);
        CountDownLatch endLatch = new CountDownLatch(threadCount);

        List<User> students = new ArrayList<>();
        for (int i = 0; i < threadCount; i++) {
            User s = User.builder()
                    .username("student_concurrent_" + i)
                    .email("student_concurrent_" + i + "@engonow.com")
                    .password("$2a$10$P7X1Y9j2m.Y4kO.6v.hUde5JzG5H8N9l3v/H2j8q8V9v8j6H8N9l3")
                    .fullName("Student Concurrent " + i)
                    .phoneNumber("091234567" + i)
                    .isActive(true)
                    .build();
            students.add(userRepository.save(s));
        }

        List<Future<Integer>> futures = new ArrayList<>();

        for (int i = 0; i < threadCount; i++) {
            final User studentForThread = students.get(i);
            futures.add(executorService.submit(() -> {
                startLatch.await();
                try {
                    BookingRequestDTO requestDTO = new BookingRequestDTO(
                            availableSlot.getId(),
                            studentForThread.getId(),
                            "Concurrent booking attempt"
                    );

                    return mockMvc.perform(post("/api/v1/bookings")
                                    .contentType(MediaType.APPLICATION_JSON)
                                    .content(objectMapper.writeValueAsString(requestDTO)))
                            .andReturn()
                            .getResponse()
                            .getStatus();
                } finally {
                    endLatch.countDown();
                }
            }));
        }

        // Start all threads simultaneously
        startLatch.countDown();
        boolean completed = endLatch.await(10, TimeUnit.SECONDS);
        assertTrue(completed, "Concurrency test timed out");

        int successCount = 0;
        int failureCount = 0;

        for (Future<Integer> future : futures) {
            int status = future.get();
            if (status == 201) {
                successCount++;
            } else if (status == 400 || status == 409) {
                failureCount++;
            }
        }

        executorService.shutdown();

        // Exactly one booking must succeed, and threadCount - 1 must fail
        assertEquals(1, successCount, "Exactly one booking request should succeed");
        assertEquals(threadCount - 1, failureCount, "All other bookings should fail");

        // Verify only one booking is persisted in database
        List<MockTestBooking> bookings = bookingRepository.findAll();
        assertEquals(1, bookings.size());
    }
}
