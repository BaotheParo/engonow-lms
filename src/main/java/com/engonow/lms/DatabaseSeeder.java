package com.engonow.lms;

import com.engonow.lms.entity.*;
import com.engonow.lms.enums.*;
import com.engonow.lms.repository.*;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.ArrayList;

@Component
public class DatabaseSeeder {

    private final UserRepository userRepository;
    private final ExamRepository examRepository;
    private final TutorAvailabilitySlotRepository slotRepository;
    private final MockTestBookingRepository bookingRepository;
    private final SpeakingSessionResultRepository speakingSessionResultRepository;
    private final TestSubmissionRepository testSubmissionRepository;

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
        System.out.println("[SEED] Clearing existing data...");
        testSubmissionRepository.deleteAll();
        speakingSessionResultRepository.deleteAll();
        bookingRepository.deleteAll();
        slotRepository.deleteAll();
        examRepository.deleteAll();
        userRepository.deleteAll();

        // Flush immediately to execute DELETE statements in DB before executing INSERTs
        testSubmissionRepository.flush();
        speakingSessionResultRepository.flush();
        bookingRepository.flush();
        slotRepository.flush();
        examRepository.flush();
        userRepository.flush();

        System.out.println("[SEED] Seeding fresh test data...");

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
                .teacher(teacher)
                .startTime(LocalDateTime.now().plusDays(1))
                .endTime(LocalDateTime.now().plusDays(1).plusHours(1))
                .status(SlotStatus.BOOKED)
                .notes("Slot for speaking practice")
                .build();
        slot = slotRepository.save(slot);

        // 4. Booking
        MockTestBooking booking = MockTestBooking.builder()
                .student(student)
                .slot(slot)
                .status(BookingStatus.CONFIRMED)
                .studentNotes("I want to practice Part 2 feedback.")
                .build();
        booking = bookingRepository.save(booking);

        System.out.println("[SEED] Database seeding complete.");
        System.out.println("[SEED] Test IDs: examId = " + exam.getId() + ", studentId = " + student.getId() + ", bookingId/sessionId = " + booking.getId());
    }
}
