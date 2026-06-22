package com.engonow.lms.repository;

import com.engonow.lms.entity.TestSubmission;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

@Repository
public interface TestSubmissionRepository extends JpaRepository<TestSubmission, Long> {

    /**
     * Load submission + all per-question details in one query.
     * Used for rendering the full report card.
     */
    @Query("""
           SELECT ts FROM TestSubmission ts
           JOIN FETCH ts.details d
           WHERE ts.id = :id
           ORDER BY d.questionNumber ASC
           """)
    Optional<TestSubmission> findByIdWithDetails(@Param("id") Long id);

    /**
     * Student history: load submission headers only (no detail rows).
     * Details are fetched on-demand when viewing a specific submission.
     */
    @Query("""
           SELECT ts FROM TestSubmission ts
           JOIN FETCH ts.exam e
           WHERE ts.student.id = :studentId
           ORDER BY ts.createdAt DESC
           """)
    List<TestSubmission> findByStudentIdWithExam(@Param("studentId") Long studentId);

    boolean existsByStudentIdAndExamIdAndIsGraded(Long studentId, Long examId, Boolean isGraded);
}
