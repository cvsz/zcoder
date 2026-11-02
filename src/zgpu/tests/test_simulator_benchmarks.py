from zgpu.benchmarks.run_benchmarks import benchmark_tensor_mma, benchmark_vector_add


def test_vector_add_benchmark_validates_all_elements(capsys):
    benchmark_vector_add()
    output = capsys.readouterr().out
    assert "Validation: 1024/1024 elements correct" in output
    assert "dram_reads: 64" in output
    assert "dram_writes: 32" in output


def test_tensor_mma_benchmark_checks_reference_result(capsys):
    benchmark_tensor_mma()
    assert "Simulated MMA verification PASSED!" in capsys.readouterr().out
