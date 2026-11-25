# Native history benchmark: separate settling from idle CPU

The benchmark used the interval ending at the first idle sample for both idle CPU summaries, even when the interval started before idle. The memory snapshot at that instant was already idle and stays in the memory calculation.

Use the same wholly idle intervals for both CPU summaries. Older samplers that emit no interval eligibility markers use adjacent idle samples. If no interval qualifies, report null and an interval count of zero instead of a fake zero.

This changes the benchmark report, not the application. Exact preimages are Desktop main `4f8db605940c00d48b91cd32f35f8adbc7e7a339` and M479. Exact apply/reverse checks passed. All three stock and six proposed Python unit tests passed. Four isolated cases exercised real report generation and the current Core Recorder with a fake process, sample data and clock. In one fixture, both displayed CPU numbers changed from 50% to 0% with identical memory points, sample rows and non-CPU fields. No native run or recalculation of earlier reports.
