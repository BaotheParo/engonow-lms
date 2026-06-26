package com.engonow.lms.service.impl;

import com.engonow.lms.dto.OmrAnswer;
import com.engonow.lms.dto.SubmissionResponseDTO;
import com.engonow.lms.entity.AnswerKey;
import com.engonow.lms.entity.Exam;
import com.engonow.lms.entity.SubmissionDetail;
import com.engonow.lms.entity.TestSubmission;
import com.engonow.lms.entity.User;
import com.engonow.lms.mapper.SubmissionMapper;
import com.engonow.lms.repository.ExamRepository;
import com.engonow.lms.repository.TestSubmissionRepository;
import com.engonow.lms.repository.UserRepository;
import com.engonow.lms.service.SubmissionService;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.MediaType;
import org.springframework.http.client.MultipartBodyBuilder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.reactive.function.BodyInserters;
import org.springframework.web.reactive.function.client.WebClient;

import java.io.IOException;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

@Service
public class SubmissionServiceImpl implements SubmissionService {

    private final ExamRepository examRepository;
    private final TestSubmissionRepository testSubmissionRepository;
    private final UserRepository userRepository;
    private final WebClient aiWebClient;
    private final SubmissionMapper submissionMapper;
    private final CloudinaryStorageMock cloudinaryStorageMock;

    public SubmissionServiceImpl(
            ExamRepository examRepository,
            TestSubmissionRepository testSubmissionRepository,
            UserRepository userRepository,
            @Qualifier("aiWebClient") WebClient aiWebClient,
            SubmissionMapper submissionMapper,
            CloudinaryStorageMock cloudinaryStorageMock) {
        this.examRepository = examRepository;
        this.testSubmissionRepository = testSubmissionRepository;
        this.userRepository = userRepository;
        this.aiWebClient = aiWebClient;
        this.submissionMapper = submissionMapper;
        this.cloudinaryStorageMock = cloudinaryStorageMock;
    }

    @Override
    @Transactional
    public SubmissionResponseDTO processOmrScan(Long examId, Long studentId, MultipartFile file) {
        byte[] fileBytes;
        try {
            fileBytes = file.getBytes();
        } catch (IOException e) {
            throw new RuntimeException("Failed to read file bytes from multipart file", e);
        }

        // Trigger Cloudinary Mock upload asynchronously
        cloudinaryStorageMock.uploadFileAsync(file.getOriginalFilename(), fileBytes);

        // Fetch Exam using JOIN FETCH to avoid N+1 query
        Exam exam = examRepository.findByIdWithAnswerKeys(examId)
                .orElseThrow(() -> new IllegalArgumentException("Exam not found or inactive: " + examId));

        // Fetch Student
        User student = userRepository.findById(studentId)
                .orElseThrow(() -> new IllegalArgumentException("Student not found: " + studentId));

        // Prepare Multipart request for Mock Python AI Scanner service
        MultipartBodyBuilder bodyBuilder = new MultipartBodyBuilder();
        bodyBuilder.part("exam_id", examId);
        bodyBuilder.part("file", new ByteArrayResource(fileBytes) {
            @Override
            public String getFilename() {
                return file.getOriginalFilename() != null ? file.getOriginalFilename() : "sheet.png";
            }
        });

        // Call OMR scanning microservice synchronously
        List<OmrAnswer> omrAnswers = aiWebClient.post()
                .uri("/api/v1/ai/omr-scan")
                .contentType(MediaType.MULTIPART_FORM_DATA)
                .body(BodyInserters.fromMultipartData(bodyBuilder.build()))
                .retrieve()
                .bodyToMono(new ParameterizedTypeReference<List<OmrAnswer>>() {})
                .block();

        if (omrAnswers == null) {
            throw new RuntimeException("Failed to receive response from external OMR AI service.");
        }

        // Map answer keys by question number for O(1) lookups
        Map<Integer, AnswerKey> answerKeyMap = exam.getAnswerKeys().stream()
                .collect(Collectors.toMap(AnswerKey::getQuestionNumber, Function.identity()));

        // Create parent TestSubmission entity
        TestSubmission submission = TestSubmission.builder()
                .student(student)
                .exam(exam)
                .imageUrl("http://cloudinary-mock-url/omr-scans/" + file.getOriginalFilename())
                .isGraded(true)
                .totalQuestions(exam.getTotalQuestions())
                .details(new ArrayList<>())
                .build();

        int totalCorrect = 0;

        // Process details and auto-grade
        for (OmrAnswer omrAnswer : omrAnswers) {
            AnswerKey correctKey = answerKeyMap.get(omrAnswer.questionNumber());
            if (correctKey == null) {
                continue; // Ignore questions that are not defined in the exam
            }

            boolean isCorrect = omrAnswer.studentAnswer() == correctKey.getCorrectOption();
            if (isCorrect) {
                totalCorrect++;
            }

            SubmissionDetail detail = SubmissionDetail.builder()
                    .questionNumber(omrAnswer.questionNumber())
                    .studentAnswer(omrAnswer.studentAnswer())
                    .correctAnswer(correctKey.getCorrectOption())
                    .isCorrect(isCorrect)
                    .build();

            // Link detail using helper method
            submission.addDetail(detail);
        }

        // Calculate and set final scores using BigDecimal
        submission.setScore(totalCorrect);

        BigDecimal correctCount = BigDecimal.valueOf(totalCorrect);
        BigDecimal totalCount = BigDecimal.valueOf(exam.getTotalQuestions());
        BigDecimal percentage = totalCount.compareTo(BigDecimal.ZERO) > 0
                ? correctCount.divide(totalCount, 4, RoundingMode.HALF_UP).multiply(BigDecimal.valueOf(100)).setScale(2, RoundingMode.HALF_UP)
                : BigDecimal.ZERO.setScale(2, RoundingMode.HALF_UP);

        submission.setPercentage(percentage.doubleValue());

        // Persist to Database
        TestSubmission savedSubmission = testSubmissionRepository.save(submission);

        return submissionMapper.toResponseDto(savedSubmission);
    }
}
