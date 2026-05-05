'use client'

import { useState, useCallback } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Upload, FileSpreadsheet, Check, AlertCircle } from 'lucide-react'

interface PreviewData {
  sheetName: string
  totalRows: number
  therapistCount: number
  clientCount: number
  therapists: string[]
  preview: {
    rowNumber: number
    date: string
    therapist: string
    client: string
    billingType: string
    hours: number | null
    totalFee: number | null
    paymentStatus: string
  }[]
}

interface ImportResult {
  success: boolean
  imported: number
  skipped: number
  therapists: number
  clients: number
}

export default function ImportPage() {
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<PreviewData | null>(null)
  const [result, setResult] = useState<ImportResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [mode, setMode] = useState<'append' | 'replace'>('append')
  const [dragOver, setDragOver] = useState(false)

  const handleFile = useCallback(async (f: File) => {
    setFile(f)
    setResult(null)
    setError('')
    setLoading(true)

    const formData = new FormData()
    formData.append('file', f)

    try {
      const res = await fetch('/api/import/preview', { method: 'POST', body: formData })
      const data = await res.json()

      if (!res.ok) {
        setError(data.error)
        setPreview(null)
      } else {
        setPreview(data)
      }
    } catch {
      setError('預覽失敗')
    }
    setLoading(false)
  }, [])

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setDragOver(false)
      const f = e.dataTransfer.files[0]
      if (f && (f.name.endsWith('.xlsx') || f.name.endsWith('.xls'))) {
        handleFile(f)
      } else {
        setError('請上傳 .xlsx 檔案')
      }
    },
    [handleFile]
  )

  const handleImport = async () => {
    if (!file) return
    setLoading(true)
    setError('')

    const formData = new FormData()
    formData.append('file', file)
    formData.append('mode', mode)

    try {
      const res = await fetch('/api/import', { method: 'POST', body: formData })
      const data = await res.json()

      if (!res.ok) {
        setError(data.error)
      } else {
        setResult(data)
        setPreview(null)
      }
    } catch {
      setError('匯入失敗')
    }
    setLoading(false)
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Excel 匯入</h1>

      {/* Upload area */}
      <Card>
        <CardHeader>
          <CardTitle>上傳檔案</CardTitle>
          <CardDescription>上傳月報表 Excel 檔案（.xlsx）</CardDescription>
        </CardHeader>
        <CardContent>
          <div
            className={`border-2 border-dashed rounded-lg p-12 text-center transition-colors ${
              dragOver ? 'border-primary bg-primary/5' : 'border-muted-foreground/25'
            }`}
            onDragOver={(e) => {
              e.preventDefault()
              setDragOver(true)
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
          >
            <Upload className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
            <p className="text-muted-foreground mb-2">拖曳 Excel 檔案至此處</p>
            <p className="text-sm text-muted-foreground mb-4">或</p>
            <label className="cursor-pointer">
              <Button variant="outline" asChild>
                <span>
                  <FileSpreadsheet className="h-4 w-4 mr-2" />
                  選擇檔案
                </span>
              </Button>
              <input
                type="file"
                className="hidden"
                accept=".xlsx,.xls"
                onChange={(e) => {
                  const f = e.target.files?.[0]
                  if (f) handleFile(f)
                }}
              />
            </label>
            {file && (
              <p className="mt-4 text-sm">
                已選擇：<strong>{file.name}</strong>
              </p>
            )}
          </div>
        </CardContent>
      </Card>

      {error && (
        <Card className="border-destructive">
          <CardContent className="pt-6 flex items-center gap-2 text-destructive">
            <AlertCircle className="h-5 w-5" />
            {error}
          </CardContent>
        </Card>
      )}

      {/* Preview */}
      {preview && (
        <Card>
          <CardHeader>
            <CardTitle>預覽</CardTitle>
            <CardDescription>
              工作表：{preview.sheetName} ｜ 共 {preview.totalRows} 筆資料 ｜{' '}
              {preview.therapistCount} 位心理師 ｜ {preview.clientCount} 位個案
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-wrap gap-2">
              {preview.therapists.map((t) => (
                <Badge key={t} variant="secondary">
                  {t}
                </Badge>
              ))}
            </div>

            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>列</TableHead>
                    <TableHead>日期</TableHead>
                    <TableHead>心理師</TableHead>
                    <TableHead>個案</TableHead>
                    <TableHead>收費形式</TableHead>
                    <TableHead>時數</TableHead>
                    <TableHead>金額</TableHead>
                    <TableHead>收款</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {preview.preview.map((row) => (
                    <TableRow key={row.rowNumber}>
                      <TableCell>{row.rowNumber}</TableCell>
                      <TableCell>{row.date}</TableCell>
                      <TableCell>{row.therapist}</TableCell>
                      <TableCell>{row.client}</TableCell>
                      <TableCell>{row.billingType}</TableCell>
                      <TableCell>{row.hours}</TableCell>
                      <TableCell>{row.totalFee?.toLocaleString()}</TableCell>
                      <TableCell>
                        <Badge variant={row.paymentStatus === '已收' ? 'success' : 'warning'}>
                          {row.paymentStatus}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>

            {preview.preview.length < preview.totalRows && (
              <p className="text-sm text-muted-foreground text-center">
                僅顯示前 20 筆，共 {preview.totalRows} 筆
              </p>
            )}

            <div className="flex items-center gap-4 pt-4 border-t">
              <div className="flex items-center gap-2">
                <label className="text-sm font-medium">匯入模式：</label>
                <select
                  value={mode}
                  onChange={(e) => setMode(e.target.value as 'append' | 'replace')}
                  className="border rounded-md px-3 py-1.5 text-sm"
                >
                  <option value="append">新增（保留現有資料）</option>
                  <option value="replace">取代（刪除舊匯入資料）</option>
                </select>
              </div>
              <Button onClick={handleImport} disabled={loading}>
                {loading ? '匯入中...' : `確認匯入 ${preview.totalRows} 筆`}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Result */}
      {result && (
        <Card className="border-green-500">
          <CardContent className="pt-6">
            <div className="flex items-center gap-2 text-green-700 mb-4">
              <Check className="h-5 w-5" />
              <span className="font-medium">匯入完成</span>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div>
                <p className="text-sm text-muted-foreground">已匯入</p>
                <p className="text-2xl font-bold">{result.imported}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">略過</p>
                <p className="text-2xl font-bold">{result.skipped}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">心理師</p>
                <p className="text-2xl font-bold">{result.therapists}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">個案</p>
                <p className="text-2xl font-bold">{result.clients}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
