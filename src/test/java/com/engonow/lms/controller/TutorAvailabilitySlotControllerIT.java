package com.engonow.lms.controller;

import com.engonow.lms.entity.TutorAvailabilitySlot;
import com.engonow.lms.entity.User;
import com.engonow.lms.enums.SlotStatus;
import com.engonow.lms.repository.TutorAvailabilitySlotRepository;
import com.engonow.lms.repository.UserRepository;
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

import static org.hamcrest.Matchers.hasSize;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
public class TutorAvailabilitySlotControllerIT {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private TutorAvailabilitySlotRepository slotRepository;

    private User tutor;
    private TutorAvailabilitySlot availableSlot1;
    private TutorAvailabilitySlot availableSlot2;
    private TutorAvailabilitySlot bookedSlot;

    @BeforeEach
    public void setUp() {
        slotRepository.deleteAllInBatch();
        userRepository.deleteAllInBatch();

        tutor = User.builder()
                .username("tutor_slots_test")
                .email("tutor_slots@engonow.com")
                .password("$2a$10$P7X1Y9j2m.Y4kO.6v.hUde5JzG5H8N9l3v/H2j8q8V9v8j6H8N9l3")
                .fullName("Tutor Slots Test")
                .phoneNumber("0987654320")
                .isActive(true)
                .build();
        tutor = userRepository.save(tutor);

        // AVAILABLE Slot today + 1 day
        availableSlot1 = TutorAvailabilitySlot.builder()
                .tutor(tutor)
                .slotDate(LocalDate.now().plusDays(1))
                .startTime(LocalTime.of(9, 0))
                .endTime(LocalTime.of(10, 0))
                .slotStatus(SlotStatus.AVAILABLE)
                .build();
        availableSlot1 = slotRepository.save(availableSlot1);

        // AVAILABLE Slot today + 3 days
        availableSlot2 = TutorAvailabilitySlot.builder()
                .tutor(tutor)
                .slotDate(LocalDate.now().plusDays(3))
                .startTime(LocalTime.of(14, 0))
                .endTime(LocalTime.of(15, 0))
                .slotStatus(SlotStatus.AVAILABLE)
                .build();
        availableSlot2 = slotRepository.save(availableSlot2);

        // BOOKED Slot today + 2 days (should not be returned as available)
        bookedSlot = TutorAvailabilitySlot.builder()
                .tutor(tutor)
                .slotDate(LocalDate.now().plusDays(2))
                .startTime(LocalTime.of(10, 0))
                .endTime(LocalTime.of(11, 0))
                .slotStatus(SlotStatus.BOOKED)
                .build();
        bookedSlot = slotRepository.save(bookedSlot);
    }

    @AfterEach
    public void cleanUp() {
        slotRepository.deleteAllInBatch();
        userRepository.deleteAllInBatch();
    }

    @Test
    public void testGetAvailableSlots_NoFilters() throws Exception {
        mockMvc.perform(get("/api/v1/slots/available")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.content", hasSize(2)))
                .andExpect(jsonPath("$.content[0].id").value(availableSlot1.getId()))
                .andExpect(jsonPath("$.content[1].id").value(availableSlot2.getId()));
    }

    @Test
    public void testGetAvailableSlots_WithDateFilters() throws Exception {
        LocalDate filterDate = LocalDate.now().plusDays(2);
        mockMvc.perform(get("/api/v1/slots/available")
                        .param("startDate", filterDate.toString())
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.content", hasSize(1)))
                .andExpect(jsonPath("$.content[0].id").value(availableSlot2.getId()));
    }

    @Test
    public void testGetAvailableSlots_WithTutorFilter() throws Exception {
        mockMvc.perform(get("/api/v1/slots/available")
                        .param("tutorId", tutor.getId().toString())
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.content", hasSize(2)));
    }
}
