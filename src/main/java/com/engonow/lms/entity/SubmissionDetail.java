package com.engonow.lms.entity;

import com.engonow.lms.enums.AnswerOption;
import jakarta.persistence.*;
import lombok.*;

/**
 * One row per question in a student's OMR-scanned exam attempt.
 *
 * Design notes:
 *  - studentAnswer can be null if OMR detected no mark (unanswered question).
 *    We use @Enumerated(STRING) but allow null via nullable=true.
 *  - isCorrect is computed during auto-grading (OMR answer vs AnswerKey).
 *    Stored to avoid recomputation on every report load.
 *  - correctOption is denormalized from AnswerKey at grading time so the report
 *    can show "Your answer: B, Correct: C" without joining AnswerKey.
 */
@Entity
@Table(name = "submission_details",
       uniqueConstraints = @UniqueConstraint(
           name = "uk_submission_question",
           columnNames = {"submission_id", "question_number"}
       ))
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class SubmissionDetail {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "submission_id", nullable = false,
                foreignKey = @ForeignKey(name = "fk_detail_submission"))
    private TestSubmission submission;

    @Column(name = "question_number", nullable = false)
    private Integer questionNumber;

    /**
     * The option the student filled in (or null = unanswered).
     */
    @Enumerated(EnumType.STRING)
    @Column(name = "student_answer", length = 1)
    private AnswerOption studentAnswer;

    /**
     * Denormalized copy of the correct answer for fast report rendering.
     */
    @Enumerated(EnumType.STRING)
    @Column(name = "correct_answer", nullable = false, length = 1)
    private AnswerOption correctAnswer;

    /**
     * Computed at grading time: studentAnswer == correctAnswer.
     */
    @Column(name = "is_correct", nullable = false)
    @Builder.Default
    private Boolean isCorrect = false;
}
