package com.engonow.lms.entity;

import com.engonow.lms.enums.ExamType;
import jakarta.persistence.*;
import lombok.*;

import java.util.ArrayList;
import java.util.List;

/**
 * Represents a Listening or Reading exam paper.
 *
 * Design notes:
 *  - @OneToMany(mappedBy, cascade=ALL, orphanRemoval=true): AnswerKeys are
 *    owned by the Exam. Deleting an Exam cascades to its AnswerKeys.
 *    orphanRemoval=true ensures detached AnswerKey rows are also deleted.
 *
 *  - LAZY fetch on answerKeys: an Exam summary list should NOT bulk-load all
 *    answer keys. Only the grading service needs them, and it will call
 *    findByIdWithAnswerKeys() which uses JOIN FETCH.
 *
 *  - totalQuestions is a denormalized count for fast display without loading
 *    the entire answerKeys collection.
 */
@Entity
@Table(name = "exams")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class Exam extends BaseEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "title", nullable = false, length = 200)
    private String title;

    @Enumerated(EnumType.STRING)
    @Column(name = "exam_type", nullable = false, length = 20)
    private ExamType examType;

    @Column(name = "total_questions", nullable = false)
    private Integer totalQuestions;

    @Column(name = "duration_minutes", nullable = false)
    private Integer durationMinutes;

    @Column(name = "description", columnDefinition = "TEXT")
    private String description;

    @Builder.Default
    @Column(name = "is_active", nullable = false)
    private Boolean isActive = true;

    /**
     * Bidirectional @OneToMany.
     * The "mappedBy" attribute points to the field name in AnswerKey that owns
     * the FK column (exam_id). This side is the INVERSE side — it holds no column.
     */
    @OneToMany(
        mappedBy      = "exam",
        cascade       = CascadeType.ALL,
        orphanRemoval = true,
        fetch         = FetchType.LAZY
    )
    @OrderBy("questionNumber ASC")   // DB-level ordering, avoids in-memory sort
    @Builder.Default
    private List<AnswerKey> answerKeys = new ArrayList<>();

    // ── Helper Methods ────────────────────────────────────────────────────

    public void addAnswerKey(AnswerKey key) {
        key.setExam(this);
        this.answerKeys.add(key);
    }

    public void removeAnswerKey(AnswerKey key) {
        key.setExam(null);
        this.answerKeys.remove(key);
    }
}
