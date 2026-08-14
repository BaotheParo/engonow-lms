package com.engonow.lms.writing.domain.entity;

import com.engonow.lms.writing.domain.enums.SubmissionStatus;
import com.engonow.lms.writing.domain.enums.TaskType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import org.hibernate.annotations.ColumnDefault;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.UpdateTimestamp;
import org.hibernate.annotations.UuidGenerator;

import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

/**
 * Immutable-input aggregate root for a student's writing attempt. Only its
 * processing status and optimistic-lock version change after creation.
 */
@Entity
@Table(
    name = "writing_submissions",
    indexes = {
        @Index(name = "idx_writing_submissions_student_id", columnList = "student_id"),
        @Index(name = "idx_writing_submissions_status", columnList = "status")
    }
)
@Getter
@Setter
@NoArgsConstructor
public class WritingSubmission {

    @Id
    @GeneratedValue
    @UuidGenerator
    @Column(name = "id", nullable = false, updatable = false)
    private UUID id;

    @NotNull
    @Column(name = "student_id", nullable = false, updatable = false)
    private UUID studentId;

    @NotNull
    @Enumerated(EnumType.STRING)
    @Column(name = "task_type", nullable = false, updatable = false, length = 20)
    private TaskType taskType;

    @NotBlank
    @Column(name = "task_prompt", nullable = false, updatable = false, columnDefinition = "TEXT")
    private String taskPrompt;

    @NotBlank
    @Column(name = "essay_text", nullable = false, updatable = false, columnDefinition = "TEXT")
    private String essayText;

    @NotNull
    @Min(0)
    @Column(name = "word_count", nullable = false, updatable = false)
    private Integer wordCount;

    @NotNull
    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 20)
    private SubmissionStatus status = SubmissionStatus.PENDING;

    @CreationTimestamp
    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @UpdateTimestamp
    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    @Version
    @Column(name = "version", nullable = false)
    private Long version = 0L;

    public void markAsProcessing() {
        status = SubmissionStatus.PROCESSING;
    }

    public void markAsScored() {
        status = SubmissionStatus.SCORED;
    }

    public void markAsFailed() {
        status = SubmissionStatus.FAILED;
    }

    /**
     * Persistent identity equality: transient instances are never equal, and
     * an assigned database identifier remains stable across persistence states.
     */
    @Override
    public final boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof WritingSubmission that)) {
            return false;
        }
        return id != null && Objects.equals(id, that.id);
    }

    /** Uses a stable class-level hash until and after the identifier is assigned. */
    @Override
    public final int hashCode() {
        return getClass().hashCode();
    }
}
