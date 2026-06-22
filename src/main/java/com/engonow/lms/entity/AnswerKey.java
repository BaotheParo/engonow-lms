package com.engonow.lms.entity;

import com.engonow.lms.enums.AnswerOption;
import jakarta.persistence.*;
import lombok.*;

/**
 * Stores the correct answer for a single question within an Exam.
 *
 * Design notes:
 *  - This is the "owning side" of the Exam-AnswerKey @OneToMany relationship.
 *    It holds the FK column (exam_id) physically in the table.
 *
 *  - @ManyToOne(fetch=LAZY): the parent Exam is not loaded when we query a list
 *    of AnswerKeys in isolation. Always LAZY on @ManyToOne unless proven otherwise.
 *
 *  - Unique constraint on (exam_id, question_number) prevents duplicate entries
 *    for the same question in the same exam.
 *
 *  - correctOption stored as STRING enum for readability (A/B/C/D).
 */
@Entity
@Table(name = "answer_keys",
       uniqueConstraints = @UniqueConstraint(
           name = "uk_exam_question",
           columnNames = {"exam_id", "question_number"}
       ))
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class AnswerKey {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    /**
     * Owning side: holds the FK column.
     * LAZY: do not join-fetch Exam unless explicitly needed by a named query.
     */
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "exam_id", nullable = false,
                foreignKey = @ForeignKey(name = "fk_answer_key_exam"))
    private Exam exam;

    @Column(name = "question_number", nullable = false)
    private Integer questionNumber;

    @Enumerated(EnumType.STRING)
    @Column(name = "correct_option", nullable = false, length = 1)
    private AnswerOption correctOption;
}
