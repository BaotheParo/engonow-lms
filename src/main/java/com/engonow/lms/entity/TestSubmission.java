package com.engonow.lms.entity;

import jakarta.persistence.*;
import lombok.*;

import java.util.ArrayList;
import java.util.List;

/**
 * Represents the header record for one student's OMR-scanned exam submission.
 *
 * Design notes:
 *  - This is the "parent" in the parent-child relationship with SubmissionDetail.
 *  - score and percentage are denormalized totals computed at grading time and
 *    stored here for fast retrieval without recalculating from detail rows.
 *  - imageUrl stores the Cloudinary/S3 URL of the uploaded answer sheet photo.
 *  - SubmissionDetails: cascade=ALL + orphanRemoval — if we re-grade a submission
 *    we can wipe its detail rows and re-insert cleanly.
 *  - Extends BaseEntity for @CreatedDate / @LastModifiedDate (audit trail).
 */
@Entity
@Table(name = "test_submissions",
       indexes = {
           @Index(name = "idx_submission_student", columnList = "student_id"),
           @Index(name = "idx_submission_exam",    columnList = "exam_id")
       })
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class TestSubmission extends BaseEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "student_id", nullable = false,
                foreignKey = @ForeignKey(name = "fk_submission_student"))
    private User student;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "exam_id", nullable = false,
                foreignKey = @ForeignKey(name = "fk_submission_exam"))
    private Exam exam;

    @Column(name = "image_url", length = 512)
    private String imageUrl;

    @Column(name = "score")
    private Integer score;

    @Column(name = "total_questions")
    private Integer totalQuestions;

    @Column(name = "percentage", precision = 5)
    private Double percentage;

    @Column(name = "is_graded", nullable = false)
    @Builder.Default
    private Boolean isGraded = false;

    @OneToMany(
        mappedBy      = "submission",
        cascade       = CascadeType.ALL,
        orphanRemoval = true,
        fetch         = FetchType.LAZY
    )
    @OrderBy("questionNumber ASC")
    @Builder.Default
    private List<SubmissionDetail> details = new ArrayList<>();

    // ── Helper Methods ────────────────────────────────────────────────────

    public void addDetail(SubmissionDetail detail) {
        detail.setSubmission(this);
        this.details.add(detail);
    }

    public void clearDetails() {
        this.details.forEach(d -> d.setSubmission(null));
        this.details.clear();
    }
}
