package com.engonow.lms;

import com.engonow.lms.entity.*;
import com.engonow.lms.enums.*;
import com.engonow.lms.repository.*;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.ArrayList;

@Component
@Slf4j
public class DatabaseSeeder {

    private final UserRepository userRepository;
    private final ExamRepository examRepository;
    private final TutorAvailabilitySlotRepository slotRepository;
    private final MockTestBookingRepository bookingRepository;
    private final SpeakingSessionResultRepository speakingSessionResultRepository;
    private final TestSubmissionRepository testSubmissionRepository;

    @PersistenceContext
    private EntityManager entityManager;

    public DatabaseSeeder(
            UserRepository userRepository,
            ExamRepository examRepository,
            TutorAvailabilitySlotRepository slotRepository,
            MockTestBookingRepository bookingRepository,
            SpeakingSessionResultRepository speakingSessionResultRepository,
            TestSubmissionRepository testSubmissionRepository) {
        this.userRepository = userRepository;
        this.examRepository = examRepository;
        this.slotRepository = slotRepository;
        this.bookingRepository = bookingRepository;
        this.speakingSessionResultRepository = speakingSessionResultRepository;
        this.testSubmissionRepository = testSubmissionRepository;
    }

    @Transactional
    public void seed() {
        log.info("[SEED] Clearing existing data...");
        // Disable foreign key checks to allow fast and safe truncation/deletion of all tables
        entityManager.createNativeQuery("SET FOREIGN_KEY_CHECKS = 0").executeUpdate();

        testSubmissionRepository.deleteAllInBatch();
        speakingSessionResultRepository.deleteAllInBatch();
        bookingRepository.deleteAllInBatch();
        slotRepository.deleteAllInBatch();
        examRepository.deleteAllInBatch();
        userRepository.deleteAllInBatch();

        // Re-enable foreign key checks after clear
        entityManager.createNativeQuery("SET FOREIGN_KEY_CHECKS = 1").executeUpdate();

        log.info("[SEED] Seeding fresh test data...");

        // 1. Users
        User student = User.builder()
                .username("student")
                .email("student@engonow.com")
                .password("$2a$10$P7X1Y9j2m.Y4kO.6v.hUde5JzG5H8N9l3v/H2j8q8V9v8j6H8N9l3")
                .fullName("Nguyen Van Student")
                .phoneNumber("0912345678")
                .isActive(true)
                .build();
        student = userRepository.save(student);

        User teacher = User.builder()
                .username("teacher")
                .email("teacher@engonow.com")
                .password("$2a$10$P7X1Y9j2m.Y4kO.6v.hUde5JzG5H8N9l3v/H2j8q8V9v8j6H8N9l3")
                .fullName("Tran Van Teacher")
                .phoneNumber("0987654321")
                .isActive(true)
                .build();
        teacher = userRepository.save(teacher);

        // 2. Exam
        Exam exam = Exam.builder()
                .title("IELTS Practice Listening Test 1")
                .examType(ExamType.LISTENING)
                .totalQuestions(40)
                .durationMinutes(30)
                .isActive(true)
                .answerKeys(new ArrayList<>())
                .build();

        AnswerOption[] options = {AnswerOption.A, AnswerOption.B, AnswerOption.C, AnswerOption.D};
        for (int i = 1; i <= 40; i++) {
            AnswerKey key = AnswerKey.builder()
                    .questionNumber(i)
                    .correctOption(options[(i - 1) % 4])
                    .build();
            exam.addAnswerKey(key);
        }
        exam = examRepository.save(exam);

        // 3. Slot
        TutorAvailabilitySlot slot = TutorAvailabilitySlot.builder()
                .tutor(teacher)
                .slotDate(java.time.LocalDate.now().plusDays(1))
                .startTime(java.time.LocalTime.now().plusHours(1))
                .endTime(java.time.LocalTime.now().plusHours(2))
                .slotStatus(SlotStatus.BOOKED)
                .build();
        slot = slotRepository.save(slot);

        // 4. Booking
        MockTestBooking booking = MockTestBooking.builder()
                .student(student)
                .slot(slot)
                .bookingStatus(BookingStatus.CONFIRMED)
                .notes("I want to practice Part 2 feedback.")
                .build();
        booking = bookingRepository.save(booking);

        log.info("[SEED] Database seeding complete.");
        log.info("[SEED] Test IDs: examId = {}, studentId = {}, bookingId/sessionId = {}",
            exam.getId(), student.getId(), booking.getId());
    }
}
