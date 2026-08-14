package com.engonow.lms.writing.repository;

import com.engonow.lms.writing.domain.entity.WritingSubmission;
import com.engonow.lms.writing.domain.enums.SubmissionStatus;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

@Repository
public interface WritingSubmissionRepository
    extends JpaRepository<WritingSubmission, UUID>, JpaSpecificationExecutor<WritingSubmission> {

    Page<WritingSubmission> findByStudentId(UUID studentId, Pageable pageable);

    Page<WritingSubmission> findByStudentIdAndStatus(
        UUID studentId,
        SubmissionStatus status,
        Pageable pageable
    );

    Optional<WritingSubmission> findByIdAndStudentId(UUID id, UUID studentId);

    @Query("SELECT s FROM WritingSubmission s WHERE s.status = :status AND s.createdAt < :cutoffTime")
    List<WritingSubmission> findStaleSubmissions(
        @Param("status") SubmissionStatus status,
        @Param("cutoffTime") Instant cutoffTime,
        Pageable pageable
    );
}
