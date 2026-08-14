package com.engonow.lms.writing.repository;

import com.engonow.lms.writing.domain.entity.WritingResult;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

@Repository
public interface WritingResultRepository extends JpaRepository<WritingResult, UUID> {

    Optional<WritingResult> findBySubmissionIdAndIsCurrentTrue(UUID submissionId);

    List<WritingResult> findBySubmissionIdOrderByResultVersionDesc(UUID submissionId);

    @Transactional
    @Modifying
    @Query("UPDATE WritingResult r SET r.isCurrent = false "
        + "WHERE r.submission.id = :submissionId AND r.isCurrent = true")
    int invalidateCurrentResult(@Param("submissionId") UUID submissionId);

    @Query("SELECT AVG(r.overallBand) FROM WritingResult r "
        + "WHERE r.submission.studentId = :studentId AND r.isCurrent = true")
    Optional<BigDecimal> calculateAverageBandForStudent(@Param("studentId") UUID studentId);
}
