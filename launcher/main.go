// NobuNotes.exe - tiny launcher.
//
// First run: unpacks the bundled Python runtime from setup\runtime.zip.001, .002, ...
// Every run: starts runtime\pythonw.exe app\nobu_main.py with no console window.
package main

import (
	"archive/zip"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strings"
	"syscall"
	"unsafe"
)

var user32 = syscall.NewLazyDLL("user32.dll")

func msgBox(title, text string, flags uintptr) {
	t, _ := syscall.UTF16PtrFromString(text)
	c, _ := syscall.UTF16PtrFromString(title)
	user32.NewProc("MessageBoxW").Call(0, uintptr(unsafe.Pointer(t)), uintptr(unsafe.Pointer(c)), flags)
}

func fail(text string) {
	msgBox("Nobu Notes", text, 0x10) // MB_ICONERROR
	os.Exit(1)
}

// multiReaderAt presents several files as one big file (the split zip).
type multiReaderAt struct {
	files   []*os.File
	offsets []int64
	total   int64
}

func (m *multiReaderAt) ReadAt(p []byte, off int64) (int, error) {
	n := 0
	for n < len(p) {
		pos := off + int64(n)
		if pos >= m.total {
			return n, io.EOF
		}
		i := sort.Search(len(m.offsets), func(i int) bool { return m.offsets[i] > pos }) - 1
		got, err := m.files[i].ReadAt(p[n:], pos-m.offsets[i])
		n += got
		if err != nil && err != io.EOF {
			return n, err
		}
		if got == 0 {
			return n, io.EOF
		}
	}
	return n, nil
}

func unpack(setupDir, dest string) error {
	parts, _ := filepath.Glob(filepath.Join(setupDir, "runtime.zip.*"))
	if len(parts) == 0 {
		return errors.New("the setup files (setup\\runtime.zip.001 ...) are missing")
	}
	sort.Strings(parts)
	m := &multiReaderAt{}
	for _, p := range parts {
		f, err := os.Open(p)
		if err != nil {
			return err
		}
		defer f.Close()
		st, _ := f.Stat()
		m.files = append(m.files, f)
		m.offsets = append(m.offsets, m.total)
		m.total += st.Size()
	}
	zr, err := zip.NewReader(m, m.total)
	if err != nil {
		return fmt.Errorf("the setup files are damaged or incomplete (%v)", err)
	}
	tmp := dest + ".tmp"
	os.RemoveAll(tmp)
	if err := os.MkdirAll(tmp, 0o755); err != nil {
		return err
	}
	base := filepath.Clean(tmp) + string(os.PathSeparator)
	buf := make([]byte, 1<<20)
	for _, zf := range zr.File {
		target := filepath.Join(tmp, filepath.FromSlash(zf.Name))
		if !strings.HasPrefix(target+string(os.PathSeparator), base) {
			return fmt.Errorf("unsafe path in archive: %s", zf.Name)
		}
		if zf.FileInfo().IsDir() {
			os.MkdirAll(target, 0o755)
			continue
		}
		if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
			return err
		}
		rc, err := zf.Open()
		if err != nil {
			return err
		}
		out, err := os.Create(target)
		if err != nil {
			rc.Close()
			return err
		}
		_, err = io.CopyBuffer(out, rc, buf)
		rc.Close()
		out.Close()
		if err != nil {
			return err
		}
	}
	os.RemoveAll(dest)
	return os.Rename(tmp, dest)
}

func main() {
	exe, err := os.Executable()
	if err != nil {
		fail("Cannot work out where Nobu Notes is installed.")
	}
	if r, err := filepath.EvalSymlinks(exe); err == nil {
		exe = r
	}
	home := filepath.Dir(exe)
	rt := filepath.Join(home, "runtime")
	py := filepath.Join(rt, "pythonw.exe")
	script := filepath.Join(home, "app", "nobu_main.py")

	if _, err := os.Stat(script); err != nil {
		fail("The program files are missing:\n" + script + "\n\nKeep NobuNotes.exe together with the 'app' and 'setup' folders.")
	}
	if _, err := os.Stat(py); err != nil {
		msgBox("Nobu Notes", "Welcome! Nobu Notes will now unpack its components.\n\nThis happens only once and takes about a minute. "+
			"Click OK, then wait - the program opens by itself when it is ready.", 0x40)
		if err := unpack(filepath.Join(home, "setup"), rt); err != nil {
			fail("Could not unpack the components:\n\n" + err.Error())
		}
		if _, err := os.Stat(py); err != nil {
			fail("Unpacking finished but the Python runtime was not found.")
		}
	}

	cmd := exec.Command(py, append([]string{script}, os.Args[1:]...)...)
	cmd.Dir = home
	env := []string{}
	for _, e := range os.Environ() {
		u := strings.ToUpper(e)
		if strings.HasPrefix(u, "PYTHONHOME=") || strings.HasPrefix(u, "PYTHONPATH=") {
			continue
		}
		env = append(env, e)
	}
	env = append(env, "NOBU_HOME="+home, "NOBU_EXE="+exe, "PYTHONNOUSERSITE=1", "PYTHONIOENCODING=utf-8")
	cmd.Env = env
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true, CreationFlags: 0x08000000}
	if err := cmd.Start(); err != nil {
		fail("Could not start Nobu Notes:\n\n" + err.Error())
	}
	cmd.Process.Release()
}
