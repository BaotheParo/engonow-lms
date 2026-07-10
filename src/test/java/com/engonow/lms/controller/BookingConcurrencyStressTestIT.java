package com.engonow.lms.controller;

import com.engonow.lms.dto.BookingRequestDTO;
import com.engonow.lms.entity.MockTestBooking;
import com.engonow.lms.entity.TutorAvailabilitySlot;
import com.engonow.lms.entity.User;
import com.engonow.lms.enums.SlotStatus;
import com.engonow.lms.repository.MockTestBookingRepository;
import com.engonow.lms.repository.TutorAvailabilitySlotRepository;
import com.engonow.lms.repository.UserRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import java.time.LocalDate;
import java.time.LocalTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

@SpringBootTest(properties = "app.seeding.enabled=false")
@AutoConfigureMockMvc
@Slf4j
public class BookingConcurrencyStressTestIT {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Autowired
    private TutorAvailabilitySlotRepository tutorAvailabilitySlotRepository;

    @Autowired
    private MockTestBookingRepository mockTestBookingRepository;

    @Autowired
    private UserRepository userRepository;

    private TutorAvailabilitySlot targetSlot;
    private final List<User> students = new ArrayList<>();

    @BeforeEach
    public void setUp() {
        mockTestBookingRepository.deleteAllInBatch();
        tutorAvailabilitySlotRepository.deleteAllInBatch();
        userRepository.deleteAllInBatch();

        // Create Tutor
        User tutor = User.builder()
                .username("stress_tutor")
                .email("stress_tutor@engonow.com")
                .password("$2a$10$P7X1Y9j2m.Y4kO.6v.hUde5JzG5H8N9l3v/H2j8q8V9v8j6H8N9l3")
                .fullName("Stress Tutor")
                .phoneNumber("0987654301")
                .isActive(true)
                .build();
        tutor = userRepository.save(tutor);

        // Create Target Slot
        targetSlot = TutorAvailabilitySlot.builder()
                .tutor(tutor)
                .slotDate(LocalDate.now().plusDays(5))
                .startTime(LocalTime.of(15, 0))
                .endTime(LocalTime.of(16, 0))
                .slotStatus(SlotStatus.AVAILABLE)
                .build();
        targetSlot = tutorAvailabilitySlotRepository.save(targetSlot);

        // Seed exactly 50 distinct Students
        for (int i = 0; i < 50; i++) {
            User student = User.builder()
                    .username("stress_student_" + i)
                    .email("stress_student_" + i + "@engonow.com")
                    .password("$2a$10$P7X1Y9j2m.Y4kO.6v.hUde5JzG5H8N9l3v/H2j8q8V9v8j6H8N9l3")
                    .fullName("Stress Student " + i)
                    .phoneNumber("09123458" + (i < 10 ? "0" + i : i))
                    .isActive(true)
                    .build();
            students.add(userRepository.save(student));
        }
    }

    @AfterEach
    public void tearDown() {
        mockTestBookingRepository.deleteAllInBatch();
        tutorAvailabilitySlotRepository.deleteAllInBatch();
        userRepository.deleteAllInBatch();
    }

    @Test
    public void testHighLoadConcurrentBooking_ShouldGuaranteeZeroOverbookingUnder50Threads() throws Exception {
        int concurrencyLevel = 50;
        ExecutorService executorService = Executors.newFixedThreadPool(concurrencyLevel);
        CountDownLatch readyLatch = new CountDownLatch(concurrencyLevel);
        CountDownLatch startLatch = new CountDownLatch(1);
        CountDownLatch finishLatch = new CountDownLatch(concurrencyLevel);

        AtomicInteger successCount = new AtomicInteger(0);
        AtomicInteger failureCount = new AtomicInteger(0);

        for (int i = 0; i < concurrencyLevel; i++) {
            final User student = students.get(i);
            executorService.submit(() -> {
                readyLatch.countDown();
                try {
                    startLatch.await();

                    BookingRequestDTO requestDTO = new BookingRequestDTO(
                            targetSlot.getId(),
                            student.getId(),
                            "Heavy contention stress test booking attempt."
                    );

                    MvcResult result = mockMvc.perform(post("/api/v1/bookings")
                                    .contentType(MediaType.APPLICATION_JSON)
                                    .content(objectMapper.writeValueAsString(requestDTO)))
                            .andReturn();

                    int httpStatus = result.getResponse().getStatus();
                    String responseBody = result.getResponse().getContentAsString();

                    if (httpStatus == 201) {
                        successCount.incrementAndGet();
                    } else if (httpStatus == 400) {
                        @SuppressWarnings("unchecked")
                        Map<String, Object> errorMap = objectMapper.readValue(responseBody, Map.class);
                        if ("The selected slot is no longer available for booking".equals(errorMap.get("message"))) {
                            failureCount.incrementAndGet();
                        } else {
                            log.error("Unexpected 400 Bad Request error payload: {}", responseBody);
                        }
                    } else {
                        log.error("Unexpected HTTP Status Code: {} with payload: {}", httpStatus, responseBody);
                    }
                } catch (Exception e) {
                    log.error("Exception occurred during concurrent API request execution", e);
                } finally {
                    finishLatch.countDown();
                }
            });
        }

        // Wait for all threads to be ready
        boolean readyTimedOut = !readyLatch.await(10, TimeUnit.SECONDS);
        if (readyTimedOut) {
            log.warn("Stress test ready latch timed out before all threads initialized.");
        }

        // Fire starting gun
        startLatch.countDown();

        // Wait for all threads to finish execution
        boolean finishTimedOut = !finishLatch.await(30, TimeUnit.SECONDS);
        if (finishTimedOut) {
            log.warn("Stress test finish latch timed out. Some requests did not complete.");
        }

        executorService.shutdown();

        // High load contention verification
        assertEquals(1, successCount.get(), "Exactly one student booking must succeed");
        assertEquals(49, failureCount.get(), "Exactly 49 student bookings must fail with slot unavailable");
        assertEquals(1, mockTestBookingRepository.count(), "Exactly one booking record must exist in DB");

        // Verify slot status in database is BOOKED
        TutorAvailabilitySlot updatedSlot = tutorAvailabilitySlotRepository.findById(targetSlot.getId())
                .orElseThrow(() -> new AssertionError("Slot should exist in DB"));
        assertEquals(SlotStatus.BOOKED, updatedSlot.getSlotStatus());
    }
}
